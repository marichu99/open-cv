import mimetypes
import os
import re
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db, socketio
from app.models import Agent, PollingStation, FormSubmission, VoteRecord, VerificationLog
from app.models.submission import FORM_LEVEL_LETTERS, TALLIED_STATUSES
from app.services.storage import LocalStorage, GCSStorage
from app.services.dedup import find_existing_approved, supersede
from app.services.extraction_queue import enqueue_extraction
from app.services.pdf import is_pdf, pdf_first_page_to_image
from app.services.image_quality import looks_blank
from app.utils.caching import cache_control
from app.utils.errors import ApiError
from app.utils.validation import parse_vote_count

bp = Blueprint("submissions", __name__, url_prefix="/api/submissions")


def can_view_submission(submission: FormSubmission, identity: str, role: str) -> bool:
    """Who may read a submission's detail/image/logs. `campaign_manager` is
    scoped to submissions from agents *they* assigned (Agent.assigned_by —
    see api/agents.py's assign_station); `aspirant` is the same cascade one
    hop further — agents whose campaign manager registered under THAT
    aspirant (Agent.assigned_by -> Agent.aspirant_id), mirroring
    api/agents.py's list_agents scoping so an aspirant can't see another
    aspirant's campaign any more than they can see their agents; `agent`
    only ever sees their own upload, same as before this function existed."""
    if role in ("coordinator", "admin"):
        return True
    if role == "campaign_manager":
        return submission.agent is not None and str(submission.agent.assigned_by) == str(identity)
    if role == "aspirant":
        return (
            submission.agent is not None
            and submission.agent.assigned_by is not None
            and Agent.query.filter_by(id=submission.agent.assigned_by, role="campaign_manager", aspirant_id=identity).first()
            is not None
        )
    if role == "agent":
        return str(submission.agent_id) == str(identity)
    return False


def _scope_submissions(role: str, identity: str):
    """The campaign-manager/aspirant scoping both list_submissions and
    discrepancy_report need — a campaign manager only ever sees submissions
    from agents *they* assigned; an aspirant, the same cascade one hop
    further. Mirrors can_view_submission's per-row check above, just as a
    query filter instead of a per-object one. coordinator/admin get
    everything (no filter applied)."""
    q = FormSubmission.query
    if role == "campaign_manager":
        q = q.join(Agent, FormSubmission.agent_id == Agent.id).filter(Agent.assigned_by == identity)
    elif role == "aspirant":
        their_cms = db.session.query(Agent.id).filter(Agent.role == "campaign_manager", Agent.aspirant_id == identity)
        q = q.join(Agent, FormSubmission.agent_id == Agent.id).filter(Agent.assigned_by.in_(their_cms))
    return q


def _arithmetic_ok(submission: FormSubmission) -> bool:
    """The IEBC form prints "Total Number of Valid Votes Cast" and "Total
    Number of Rejected Ballot Papers" as two independent counts, not one
    derived from the other — valid votes cast already excludes rejected
    ballots by definition, it's not (candidates + rejected). Summing them
    in here previously produced a false mismatch on any form with a
    nonzero rejected-ballot count whose candidate figures were actually
    correct (e.g. 168+3+140+0=311 candidates, 311 declared, 3 rejected —
    flagged as "don't add up" when it did)."""
    if submission.total_votes_cast is None:
        return False
    total = sum(v.effective_votes for v in submission.vote_records)
    return total == submission.total_votes_cast


@bp.post("/draft")
@jwt_required()
def create_draft():
    if "image" not in request.files:
        raise ApiError("image file is required")

    agent = db.session.get(Agent, get_jwt_identity())
    if not agent or not agent.positions:
        raise ApiError("No elective position assigned yet — contact your campaign manager", status_code=403)

    position_id = request.form.get("position_id")
    if not position_id:
        raise ApiError("position_id is required")
    position = next((p for p in agent.positions if str(p.id) == position_id), None)
    if not position:
        raise ApiError("Not one of your assigned positions", status_code=403)

    station_id = request.form.get("station_id")
    form_level = request.form.get("form_level", "A")
    captured_at_raw = request.form.get("captured_at")

    if form_level not in FORM_LEVEL_LETTERS:
        raise ApiError(f"form_level must be one of {FORM_LEVEL_LETTERS}")
    form_type = f"{position.form_series}{form_level}"
    station = db.session.get(PollingStation, station_id)
    if not station:
        raise ApiError("Unknown polling station", status_code=404)

    # An agent submits for the station they were posted to — nothing else.
    # Previously only `position_id` was checked against the agent's
    # assignment while `station_id` was taken from the request as-is, so any
    # authenticated agent could file a result for any of the ~24,600 polling
    # stations in the country. Agent.assigned_station_id already existed and
    # is settable only by a campaign_manager/admin (see api/agents.py); this
    # endpoint simply never consulted it.
    #
    # Deliberately strict on the unassigned case: an agent with no station is
    # not "allowed everywhere", they are not yet deployed. Mirrors the
    # no-position branch above.
    if not agent.assigned_station_id:
        raise ApiError(
            "No polling station assigned yet — contact your campaign manager",
            status_code=403,
        )
    if str(station.id) != str(agent.assigned_station_id):
        raise ApiError(
            "You can only submit forms for the polling station you're assigned to",
            status_code=403,
        )

    upload = request.files["image"]
    if is_pdf(upload):
        try:
            upload = pdf_first_page_to_image(upload)
        except ValueError as exc:
            raise ApiError(f"Could not process PDF: {exc}")

    storage = LocalStorage(current_app.config["UPLOAD_DIR"])
    image_path, sha256 = storage.save(upload)

    if looks_blank(image_path):
        try:
            os.remove(image_path)
        except OSError:
            pass
        raise ApiError(
            "This photo looks blank or unreadable — please retake it with the form clearly in frame.",
            status_code=422,
        )

    existing = FormSubmission.query.filter_by(
        station_id=station.id, form_type=form_type, image_sha256=sha256
    ).first()
    if existing:
        if existing.status not in ("draft", "processing", "extraction_failed"):
            raise ApiError("This exact image has already been uploaded for this station/form", status_code=409)
        # None of draft, still-processing, or extraction_failed is
        # "uploaded" in any sense worth protecting — the first two are
        # abandoned attempts from earlier (e.g. the agent hit Retake, or a
        # task is still in flight) that were never confirmed, and
        # extraction_failed means the pipeline itself couldn't process the
        # photo (blank/mismatched-location/etc — see models/submission.py's
        # STATUSES), which is exactly the case where the agent is expected
        # to retake or simply retry the same photo, e.g. after a location-
        # check false positive gets fixed server-side. The DB's unique
        # constraint on (station_id, form_type, image_sha256) means the new
        # upload can't coexist with any of these, so replace rather than
        # block with a misleading "already uploaded" error.
        db.session.delete(existing)
        db.session.flush()

    if current_app.config["STORAGE_BACKEND"] == "gcs":
        object_name = GCSStorage(current_app.config["GCS_BUCKET_NAME"]).upload(image_path, sha256)
        os.remove(image_path)
        image_path = object_name

    submission = FormSubmission(
        station_id=station.id,
        agent_id=get_jwt_identity(),
        position_id=position.id,
        form_type=form_type,
        image_path=image_path,
        image_sha256=sha256,
        captured_at=datetime.fromisoformat(captured_at_raw) if captured_at_raw else None,
        status="processing",
    )
    db.session.add(submission)
    db.session.commit()

    # Runs synchronously inline unless a Cloud Tasks queue is configured
    # (app/services/extraction_queue.py) — either way, submission.to_dict()
    # below correctly reflects whatever state it's in by the time this
    # returns: already-resolved "draft"/"extraction_failed" when run
    # inline, or still "processing" when genuinely dispatched to a queue.
    enqueue_extraction(str(submission.id))

    return jsonify(submission.to_dict()), 202


@bp.post("/<uuid:submission_id>/finalize")
@jwt_required()
def finalize(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if str(submission.agent_id) != get_jwt_identity() and get_jwt().get("role") not in ("coordinator", "admin"):
        raise ApiError("Forbidden", status_code=403)
    if submission.status == "processing":
        raise ApiError("Still processing — try again shortly", status_code=409)
    if submission.status == "extraction_failed":
        message = (submission.warnings or ["Extraction failed for this photo — please retake it."])[0]
        raise ApiError(message, status_code=422)
    if submission.status != "draft":
        raise ApiError("Submission has already been finalized")

    # The submitting agent can fix a misread figure right here in the
    # preview — the same "corrected value wins" mechanism a coordinator uses
    # in the review dialog, just applied before the submission ever leaves
    # draft status.
    corrections = (request.get_json(silent=True) or {}).get("corrections") or []
    if corrections:
        by_candidate = {str(v.candidate_id): v for v in submission.vote_records}
        for correction in corrections:
            record = by_candidate.get(str(correction.get("candidate_id")))
            if not record:
                continue
            old_value = record.effective_votes
            # Bounded and non-negative. This value goes straight into
            # tally_service.EFFECTIVE_VOTES, so an unvalidated Integer here
            # meant a single agent could add 2,147,483,647 votes — or, with a
            # negative, SUBTRACT from a candidate's national total.
            record.votes_corrected = parse_vote_count(
                correction.get("votes_corrected"), "Corrected vote count"
            )
            record.manually_overridden = True
            # One row per corrected candidate, carrying the actual old/new
            # figures — not one row for the whole batch — so a CM/aspirant
            # reading the log later sees exactly what changed, even if a
            # later coordinator correction overwrites votes_corrected again.
            db.session.add(
                VerificationLog(
                    submission_id=submission.id,
                    reviewer_id=get_jwt_identity(),
                    action="manual_correct",
                    notes="Corrected by the submitting agent before finalizing",
                    candidate_id=record.candidate_id,
                    old_value=old_value,
                    new_value=record.votes_corrected,
                )
            )

    threshold = current_app.config["CONFIDENCE_THRESHOLD"]
    duplicate = find_existing_approved(
        submission.station_id, submission.form_type, submission.stream_number, submission.id
    )

    # The agent has already seen the extracted figures and had the chance to
    # correct them (see the `corrections` handling above), so their
    # confirmation is authoritative — including over an earlier submission
    # for the same station, which this one supersedes rather than waiting on
    # a coordinator. Warnings — an arithmetic mismatch, low confidence,
    # anything Claude Vision itself flagged — still count toward the tally,
    # but stay visible for a coordinator to spot-check after the fact.
    warnings = list(submission.warnings or [])
    if not _arithmetic_ok(submission):
        warnings.append("Extracted candidate votes don't add up to the declared total votes cast")
    if float(submission.ocr_confidence_avg or 0) / 100 < threshold:
        warnings.append(f"Overall extraction confidence below the {threshold:.0%} review threshold")
    submission.warnings = warnings

    submission.status = "auto_approved"
    submission.finalized_at = datetime.now(timezone.utc)
    if duplicate:
        submission.duplicate_of = duplicate.id
        supersede(duplicate, submission, submission.agent_id, "Superseded by a newer confirmed submission for this station")

    db.session.commit()

    if submission.status in TALLIED_STATUSES:
        socketio.emit("tally_updated", {"submission_id": str(submission.id)})

    return jsonify(submission.to_dict())


@bp.get("")
@jwt_required()
def list_submissions():
    role = get_jwt().get("role")
    if role not in ("coordinator", "admin", "aspirant", "campaign_manager"):
        raise ApiError("Forbidden", status_code=403)

    q = _scope_submissions(role, get_jwt_identity())
    status = request.args.get("status")
    station_id = request.args.get("station_id")
    has_warnings = request.args.get("has_warnings")
    if status:
        q = q.filter(FormSubmission.status == status)
    if station_id:
        q = q.filter(FormSubmission.station_id == station_id)
    if has_warnings == "true":
        # Claude Vision flagged something ambiguous/inconsistent on the form
        # itself (see services/claude_vision.py) — distinct from other
        # pending-review reasons like a duplicate or a low confidence score.
        q = q.filter(db.func.json_array_length(FormSubmission.warnings) > 0)
    q = q.order_by(FormSubmission.uploaded_at.desc()).limit(200)
    return jsonify([s.to_dict(include_votes=False) for s in q])


#: (group key, label, warning substring) — arithmetic/confidence/legibility
#: discrepancies all live as plain-text entries in FormSubmission.warnings
#: (see api/submissions.py's finalize and services/claude_vision.py), so
#: they're matched by substring rather than a dedicated column. Matching
#: text, not re-deriving the check — this report explains what already
#: happened, it doesn't re-run the checks that produced it.
_WARNING_GROUPS = (
    ("arithmetic_mismatch", "Arithmetic mismatches", "don't add up"),
    ("low_confidence", "Low-confidence extractions", "confidence below"),
    ("illegible", "Flagged as hard to read", "difficult to read"),
)


def _discrepancy_label(submission: FormSubmission) -> str:
    station = submission.station.name if submission.station else "an unknown station"
    return f"{station} (Form {submission.form_type})"


def _discrepancy_when(dt) -> str:
    return dt.strftime("%d %b %Y, %H:%M") if dt else "an unknown time"


@bp.get("/discrepancy-report")
@jwt_required()
def discrepancy_report():
    """Every instance of a field agent correcting a figure, a submission
    being superseded (or restored) as a duplicate, or the extraction
    pipeline itself flagging something — an arithmetic mismatch, low
    confidence, illegible handwriting, or a wrong race/station caught
    before it ever reached the tally — grouped by kind, each with a plain-
    English sentence of what actually happened rather than just the raw
    fields. Nothing here is a new audit mechanism: it's built entirely from
    FormSubmission.warnings and VerificationLog, which every discrepancy
    already writes to as it happens (see finalize, services/dedup.py,
    api/review.py) — this endpoint is a read, not a new source of truth.

    Scoped exactly like list_submissions: a campaign manager sees only
    their own agents' submissions, an aspirant the same cascade one hop
    further (see can_view_submission's docstring) — so a campaign manager
    pulling this report only ever sees discrepancies their own agents were
    actually involved in, never another campaign's."""
    role = get_jwt().get("role")
    if role not in ("coordinator", "admin", "aspirant", "campaign_manager"):
        raise ApiError("Forbidden", status_code=403)

    submissions = _scope_submissions(role, get_jwt_identity()).all()
    by_id = {s.id: s for s in submissions}

    groups: dict[str, list[dict]] = {
        "agent_correction": [],
        "duplicate_superseded": [],
        "duplicate_reversed": [],
        "arithmetic_mismatch": [],
        "low_confidence": [],
        "illegible": [],
        "extraction_failed": [],
    }

    def _instance(s: FormSubmission, occurred_at, narration: str) -> dict:
        return {
            "submission_id": str(s.id),
            "station_name": s.station.name if s.station else None,
            "form_type": s.form_type,
            "agent_name": s.agent.full_name if s.agent else None,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
            "narration": narration,
        }

    logs = (
        VerificationLog.query.filter(
            VerificationLog.submission_id.in_(by_id.keys()),
            VerificationLog.action.in_(("manual_correct", "mark_duplicate", "approve")),
        )
        .order_by(VerificationLog.created_at.desc())
        .all()
        if by_id
        else []
    )
    for log in logs:
        submission = by_id.get(log.submission_id)
        if not submission:
            continue

        if log.action == "manual_correct":
            candidate_name = log.candidate.full_name if log.candidate else "a candidate"
            old = log.old_value if log.old_value is not None else "an unread figure"
            groups["agent_correction"].append(_instance(
                submission, log.created_at,
                f"{submission.agent.full_name if submission.agent else 'The agent'} corrected {candidate_name}'s "
                f"vote count from {old} to {log.new_value} at {_discrepancy_label(submission)}, before "
                f"finalizing, {_discrepancy_when(log.created_at)}.",
            ))
        elif log.action == "mark_duplicate":
            by_whom = f" by {log.reviewer.full_name}" if log.reviewer else ""
            note = f" — {log.notes}" if log.notes else ""
            groups["duplicate_superseded"].append(_instance(
                submission, log.created_at,
                f"{_discrepancy_label(submission)}, uploaded by "
                f"{submission.agent.full_name if submission.agent else 'an agent'}, was marked a duplicate"
                f"{by_whom} on {_discrepancy_when(log.created_at)}{note}.",
            ))
        else:  # "approve" — only ever logged here to reverse an earlier mark_duplicate (see review.py)
            groups["duplicate_reversed"].append(_instance(
                submission, log.created_at,
                f"{_discrepancy_label(submission)}'s earlier duplicate flag was reversed on manual review by "
                f"{log.reviewer.full_name if log.reviewer else 'a coordinator'} on {_discrepancy_when(log.created_at)} "
                "— it was restored to count toward the tally after all.",
            ))

    for s in submissions:
        warnings = s.warnings or []
        for key, _label, phrase in _WARNING_GROUPS:
            match = next((w for w in warnings if phrase in w), None)
            if match:
                groups[key].append(_instance(
                    s, s.finalized_at or s.uploaded_at,
                    f"{_discrepancy_label(s)}, uploaded by {s.agent.full_name if s.agent else 'an agent'}: {match}",
                ))
        if s.status == "extraction_failed":
            reason = warnings[0] if warnings else "the extraction pipeline could not process this photo"
            groups["extraction_failed"].append(_instance(
                s, s.uploaded_at,
                f"{_discrepancy_label(s)}, uploaded by {s.agent.full_name if s.agent else 'an agent'}, "
                f"never reached the tally: {reason}",
            ))

    group_labels = {
        "agent_correction": "Agent-corrected figures",
        "duplicate_superseded": "Duplicate submissions superseded",
        "duplicate_reversed": "Duplicate flags reversed on review",
        **{key: label for key, label, _phrase in _WARNING_GROUPS},
        "extraction_failed": "Extraction failed before reaching the tally",
    }
    ordered = (
        "agent_correction", "extraction_failed", "arithmetic_mismatch", "low_confidence",
        "illegible", "duplicate_superseded", "duplicate_reversed",
    )
    return jsonify({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_submissions_in_scope": len(submissions),
        "groups": [
            {
                "type": key,
                "label": group_labels[key],
                "count": len(groups[key]),
                "instances": sorted(groups[key], key=lambda i: i["occurred_at"] or "", reverse=True),
            }
            for key in ordered
            if groups[key]
        ],
    })


@bp.get("/<uuid:submission_id>")
@jwt_required()
def get_submission(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if not can_view_submission(submission, get_jwt_identity(), get_jwt().get("role")):
        raise ApiError("Forbidden", status_code=403)
    return jsonify(submission.to_dict())


def _image_response(submission: FormSubmission, as_attachment: bool = False):
    """Shared by the authenticated single-submission route and the public
    by-station-tally route below — same storage-backend branching either
    way, just the attachment/filename behavior differs."""
    download_name = None
    if as_attachment:
        ext = os.path.splitext(submission.image_path)[1] or ".jpg"
        raw_station = re.sub(r"[^A-Za-z0-9]+", "-", submission.station.name).strip("-")
        download_name = f"{raw_station}-form{submission.form_type}-stream{submission.stream_number}{ext}"

    if current_app.config["STORAGE_BACKEND"] == "gcs":
        data = GCSStorage(current_app.config["GCS_BUCKET_NAME"]).download_bytes(submission.image_path)
        mimetype = mimetypes.guess_type(submission.image_path)[0] or "application/octet-stream"
        resp = Response(data, mimetype=mimetype)
        if as_attachment:
            resp.headers["Content-Disposition"] = f'attachment; filename="{download_name}"'
        return resp
    return send_file(submission.image_path, as_attachment=as_attachment, download_name=download_name)


@bp.get("/<uuid:submission_id>/image")
@jwt_required()
def get_image(submission_id):
    submission = db.session.get(FormSubmission, submission_id)
    if not submission:
        raise ApiError("Not found", status_code=404)
    if not can_view_submission(submission, get_jwt_identity(), get_jwt().get("role")):
        raise ApiError("Forbidden", status_code=403)
    return _image_response(submission)


@bp.get("/<uuid:submission_id>/public-image")
@cache_control("public, max-age=3600")
def get_public_image(submission_id):
    """Unauthenticated — the source form image for any submission that's
    actually counting toward the public tally, so a dashboard viewer can
    pull up the original photo/scan and check it against the extracted
    numbers themselves (the whole point of a *parallel* vote tabulation:
    independently verifiable, not just trust the dashboard). Scoped to
    TALLIED_STATUSES only — same set votes_by_station() already draws
    from — so a submission that's still pending review, rejected, flagged
    as a duplicate, or failed extraction is never exposed here; 404 either
    way (never leaking) rather than a distinguishable 403."""
    submission = db.session.get(FormSubmission, submission_id)
    if not submission or submission.status not in TALLIED_STATUSES:
        raise ApiError("Not found", status_code=404)
    return _image_response(submission, as_attachment=True)

"""Real extraction backend — Claude Vision reads the candidate table straight
off the form photo/scan. Replaces the never-implemented YOLOv8 field-level
model (see git history for that stub); the whole-page prototype at
runs/train/form34a_detector was never sufficient for per-field extraction
anyway.

Uses a forced tool call (not free-text JSON parsing) so the response shape
is guaranteed — see the `claude-api` skill's guidance on structured output
via tool_choice.
"""

import base64
import io
import logging

import anthropic
from PIL import Image

from app.services.cv_pipeline import DetectedLocation, ExtractionResult, ExtractionService, FieldExtraction
from app.utils.errors import ApiError

logger = logging.getLogger(__name__)

#: Switched from claude-opus-5 to cut per-form cost — Sonnet is generally
#: strong at structured OCR-style transcription. Revisit if real-world
#: results on messy/low-contrast scans turn out worse than Opus was giving.
MODEL = "claude-sonnet-5"

#: Anthropic downscales images beyond ~1568px on the long edge before the
#: model ever sees them — a full-resolution phone photo (often 3000px+)
#: costs proportionally more tokens for pixels that get thrown away
#: server-side anyway, so shrinking client-side first is a pure cost win
#: with no legibility loss.
MAX_DIMENSION = 1568
JPEG_QUALITY = 88

#: claude-sonnet-5 rates, USD per token (Anthropic list price: $2/$10 per
#: MTok; cache write/read are the standard 1.25x / 0.1x multipliers on the
#: input rate for the default 5-minute TTL we use via `cache_control`).
_PRICE_INPUT = 2.00 / 1_000_000
_PRICE_OUTPUT = 10.00 / 1_000_000
_PRICE_CACHE_WRITE = 2.50 / 1_000_000
_PRICE_CACHE_READ = 0.20 / 1_000_000

_POSITION_LABELS = {
    "president": "President",
    "governor": "Governor",
    "senator": "Senator",
    "woman_representative": "Woman Representative",
    "member_of_parliament": "Member of Parliament",
    "mca": "Member of County Assembly (MCA)",
}

_TOOL = {
    "name": "record_form_results",
    "description": "Record the election results read from the IEBC results form image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "legible": {
                "type": "boolean",
                "description": "False if the handwriting/print is too unclear to be confident in the figures.",
            },
            "location": {
                "type": "object",
                "description": (
                    "The County/Constituency/Ward/Polling Station names exactly as printed in the "
                    "form's header section (near the top, above the results table). Use null for "
                    "any field that's missing or illegible — never guess."
                ),
                "properties": {
                    "county": {"type": ["string", "null"]},
                    "constituency": {"type": ["string", "null"]},
                    "ward": {"type": ["string", "null"]},
                    "polling_station": {"type": ["string", "null"]},
                    "stream_number": {
                        "type": ["integer", "null"],
                        "description": (
                            "If the polling station name includes a stream indicator like "
                            "'Stream 3 of 4' or '3 of 4', the stream number (3 in that example). "
                            "null if the form doesn't print one — most stations have only one stream."
                        ),
                    },
                    "stream_count": {
                        "type": ["integer", "null"],
                        "description": "The total number of streams from the same indicator (4 in '3 of 4'). null if not printed.",
                    },
                },
                "required": ["county", "constituency", "ward", "polling_station", "stream_number", "stream_count"],
                "additionalProperties": False,
            },
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Candidate's full name exactly as printed on the form."},
                        "party": {"type": ["string", "null"], "description": "Party name if printed, else null."},
                        "votes": {"type": "integer", "description": "Number of valid votes for this candidate."},
                    },
                    "required": ["name", "votes"],
                    "additionalProperties": False,
                },
            },
            "total_votes_cast": {"type": "integer", "description": "Total number of valid votes cast, as printed on the form."},
            "rejected_ballots": {"type": "integer", "description": "Total number of rejected ballot papers, as printed on the form."},
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "ONLY genuine concerns a human reviewer must double-check, e.g. an "
                    "unclear digit, an apparent alteration, or a total that does not "
                    "match the sum of candidate votes. Leave this an EMPTY array if the "
                    "form is clear and internally consistent — do NOT include "
                    "confirmations, positive notes, or restate that something checks out."
                ),
            },
        },
        "required": ["legible", "location", "candidates", "total_votes_cast", "rejected_ballots", "warnings"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _prepare_image(image_path: str) -> tuple[str, str]:
    """Returns (base64_data, media_type), downscaled to MAX_DIMENSION and
    re-encoded as JPEG — the copy sent to the API, never the stored original."""
    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            # Flatten onto white rather than letting a straight RGB convert
            # composite transparency onto black — that would degrade a
            # transparent-background PNG's actual legibility.
            rgba = img.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, (255, 255, 255))
            flattened.paste(rgba, mask=rgba.split()[-1])
            img = flattened
        else:
            img = img.convert("RGB")
        if max(img.size) > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"


def _log_usage(usage) -> None:
    """One greppable key=value INFO line per call — plain `logging.basicConfig`
    has no structured/JSON pipeline here, so this is written to be picked up
    by a Cloud Logging log-based metric via regex extraction (see
    docs/DEPLOYMENT.md) rather than relying on jsonPayload field access."""
    cache_write = usage.cache_creation_input_tokens or 0
    cache_read = usage.cache_read_input_tokens or 0
    cost_usd = (
        usage.input_tokens * _PRICE_INPUT
        + usage.output_tokens * _PRICE_OUTPUT
        + cache_write * _PRICE_CACHE_WRITE
        + cache_read * _PRICE_CACHE_READ
    )
    logger.info(
        "claude_vision_usage model=%s input_tokens=%d output_tokens=%d "
        "cache_creation_input_tokens=%d cache_read_input_tokens=%d cost_usd=%.6f",
        MODEL, usage.input_tokens, usage.output_tokens, cache_write, cache_read, cost_usd,
    )


class ClaudeExtractionService(ExtractionService):
    def __init__(self):
        self.client = anthropic.Anthropic()

    def extract(self, image_path: str, position, declared_form_type: str) -> ExtractionResult:
        image_b64, media_type = _prepare_image(image_path)

        position_label = _POSITION_LABELS.get(position.name, position.name)

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2048,
                output_config={"effort": "low"},
                system=[{
                    "type": "text",
                    "text": (
                        "You are transcribing a Kenyan IEBC election results form (Form "
                        f"{declared_form_type}) for the {position_label} race, photographed or "
                        "scanned by a field agent. First read the header section (County, "
                        "Constituency, Ward, Name of Polling Station) exactly as printed — this "
                        "is used to confirm the agent photographed the right form, so read it "
                        "verbatim rather than normalizing it. A polling station can be split into "
                        "multiple independent streams, each with its own form — if the station name "
                        "or header includes an indicator like 'Stream 3 of 4' or '3 of 4', report "
                        "stream_number and stream_count separately (do not strip it from "
                        "polling_station either — report both). Then read every candidate row in "
                        "the results table exactly as printed/handwritten, along with the total "
                        "valid votes cast and rejected ballots. Call record_form_results with "
                        "what you read. If any figure is genuinely illegible, set legible=false "
                        "and explain why in warnings rather than guessing a number."
                    ),
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "record_form_results"},
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                        {"type": "text", "text": f"Extract the results from this {position_label} form."},
                    ],
                }],
            )
        except anthropic.APIError as exc:
            logger.error("Claude Vision extraction failed: %s", exc)
            raise ApiError(
                "Form extraction is temporarily unavailable — please try again in a few minutes. "
                "If this keeps happening, let your coordinator know.",
                status_code=503,
            ) from exc

        _log_usage(response.usage)

        tool_use = next(b for b in response.content if b.type == "tool_use")
        data = tool_use.input

        legible = data["legible"]
        confidence = 0.95 if legible else 0.6
        warnings = list(data.get("warnings") or [])
        if not legible:
            warnings.append("Claude Vision flagged this form as difficult to read — verify manually.")

        votes = [
            FieldExtraction(
                candidate_name=c["name"],
                party=c.get("party"),
                votes=c["votes"],
                confidence=confidence,
            )
            for c in data["candidates"]
        ]

        location = data.get("location") or {}

        return ExtractionResult(
            form_type_detected=declared_form_type,
            votes=votes,
            total_votes_cast=data["total_votes_cast"],
            rejected_ballots=data["rejected_ballots"],
            total_votes_confidence=confidence,
            rejected_ballots_confidence=confidence,
            warnings=warnings,
            detected_location=DetectedLocation(
                county=location.get("county"),
                constituency=location.get("constituency"),
                ward=location.get("ward"),
                polling_station=location.get("polling_station"),
                stream_number=location.get("stream_number"),
                stream_count=location.get("stream_count"),
            ),
        )

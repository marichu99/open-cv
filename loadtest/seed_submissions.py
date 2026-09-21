"""Seeds FormSubmission rows for the extraction-worker k6 load test.

Uploads one sample form image to GCS once, then inserts N FormSubmission
rows in status="processing", round-robining across real seeded polling
stations so the (station_id, form_type, image_sha256) unique constraint is
never hit — every row can point at the same GCS object.

Run against the SAME DATABASE_URL / GCS_BUCKET_NAME the target
tally333-extraction-worker uses — as a one-off Cloud Run Job (same pattern
as tally333-gcs-check in docs/DEPLOYMENT.md), not from a laptop, so it
uses the deployment's own service-account credentials.

See docs/LOAD_TEST_PLAN.md before running this against anything other than
a load-test-only database.

Usage:
    python loadtest/seed_submissions.py --count 5000 --image sample_form.jpg --out submission_ids.json
"""

import argparse
import json
import sys

sys.path.insert(0, "backend")

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Agent, ElectivePosition, FormSubmission, PollingStation  # noqa: E402
from app.services.storage import GCSStorage, LocalStorage  # noqa: E402

LOADTEST_AGENT_EMAIL = "loadtest@tally333.internal"
LOADTEST_AGENT_PHONE = "+254700000000"


def _get_or_create_loadtest_agent() -> Agent:
    agent = Agent.query.filter_by(email=LOADTEST_AGENT_EMAIL).first()
    if agent:
        return agent
    agent = Agent(full_name="Load Test Agent", phone_number=LOADTEST_AGENT_PHONE, email=LOADTEST_AGENT_EMAIL)
    db.session.add(agent)
    db.session.flush()
    return agent


def _upload_sample_image(image_path: str, bucket_name: str) -> tuple[str, str]:
    """Returns (gcs_object_name, sha256_hex)."""
    local = LocalStorage("/tmp/loadtest-upload-scratch")
    with open(image_path, "rb") as fh:

        class _FakeFileStorage:
            filename = image_path
            stream = fh

            def read(self_inner):
                fh.seek(0)
                return fh.read()

        abs_path, sha256 = local.save(_FakeFileStorage())
    object_name = GCSStorage(bucket_name).upload(abs_path, sha256)
    return object_name, sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True, help="number of FormSubmission rows to seed")
    parser.add_argument("--image", required=True, help="path to one sample form image (jpg/png)")
    parser.add_argument("--position", default="president", help="ElectivePosition.name to use for every row")
    parser.add_argument("--out", default="submission_ids.json", help="where to write the generated submission ids")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        bucket_name = app.config["GCS_BUCKET_NAME"]
        if app.config["STORAGE_BACKEND"] != "gcs" or not bucket_name:
            raise SystemExit("STORAGE_BACKEND=gcs and GCS_BUCKET_NAME must be set — this seeds real GCS objects")

        position = ElectivePosition.query.filter_by(name=args.position).first()
        if not position:
            raise SystemExit(f"no ElectivePosition named {args.position!r} — has import-geography run?")

        stations = PollingStation.query.limit(args.count).all()
        if len(stations) < args.count:
            raise SystemExit(
                f"only {len(stations)} polling stations seeded, need {args.count} distinct ones "
                "to satisfy the (station_id, form_type, image_sha256) unique constraint — "
                "either seed more geography or lower --count"
            )

        print(f"uploading {args.image} to gs://{bucket_name} ...")
        object_name, sha256 = _upload_sample_image(args.image, bucket_name)
        print(f"uploaded as {object_name}")

        agent = _get_or_create_loadtest_agent()
        form_type = f"{position.form_series}A"

        ids = []
        for station in stations:
            submission = FormSubmission(
                station_id=station.id,
                agent_id=agent.id,
                position_id=position.id,
                form_type=form_type,
                image_path=object_name,
                image_sha256=sha256,
                status="processing",
            )
            db.session.add(submission)
            db.session.flush()
            ids.append(str(submission.id))

        db.session.commit()
        print(f"seeded {len(ids)} FormSubmission rows (agent_id={agent.id}, tag={LOADTEST_AGENT_EMAIL})")

    with open(args.out, "w") as fh:
        json.dump(ids, fh)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

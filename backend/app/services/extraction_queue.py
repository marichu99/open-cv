"""Dispatches a submission for extraction — a real Cloud Task when the
queue is configured (production), otherwise runs it synchronously inline
before returning (local dev, tests — no Cloud Tasks emulator needed).
"""

import json

from flask import current_app

from app.services.extraction import process_extraction


def enqueue_extraction(submission_id: str) -> None:
    queue = current_app.config["CLOUD_TASKS_QUEUE"]
    worker_url = current_app.config["EXTRACTION_WORKER_URL"]
    if not queue or not worker_url:
        process_extraction(submission_id)
        return

    from google.cloud import tasks_v2  # lazy import — only needed when the queue is actually configured

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        current_app.config["GCP_PROJECT"], current_app.config["CLOUD_TASKS_LOCATION"], queue
    )
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": worker_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"submission_id": submission_id}).encode(),
            "oidc_token": {
                "service_account_email": current_app.config["TASKS_INVOKER_SERVICE_ACCOUNT"],
                "audience": worker_url,
            },
        }
    }
    client.create_task(request={"parent": parent, "task": task})

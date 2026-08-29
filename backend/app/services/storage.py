"""Image storage abstraction.

Local filesystem for development. In production, forms still land on local
disk first — image_quality.looks_blank() and the extraction pipeline
(services/cv_pipeline.py) both need a real file path to read — and are then
pushed up to Google Cloud Storage, selected via app.config's
USE_LOCAL_STORAGE / GCS_BUCKET_NAME / GCS_CREDENTIALS_JSON. Same switch and
credentials-loading pattern as the sibling leviathan project's
document_service.py, pointed at this project's own bucket.
"""

import hashlib
import os
import uuid
from datetime import timedelta


class LocalStorage:
    def __init__(self, upload_dir: str):
        self.upload_dir = upload_dir
        os.makedirs(self.upload_dir, exist_ok=True)

    def save(self, file_storage) -> tuple[str, str]:
        """Persists an uploaded file, returns (absolute_path, sha256_hex).

        Absolute, because Flask's send_file() resolves relative paths against
        app.root_path, not the process CWD — storing a relative path here
        looks fine until the image is served back and 404s.
        """
        ext = os.path.splitext(file_storage.filename or "")[1].lower() or ".jpg"
        name = f"{uuid.uuid4()}{ext}"
        path = os.path.abspath(os.path.join(self.upload_dir, name))

        file_storage.stream.seek(0)
        data = file_storage.read()
        with open(path, "wb") as fh:
            fh.write(data)

        digest = hashlib.sha256(data).hexdigest()
        return path, digest


def _gcs_client(credentials_json: str | None):
    from google.cloud import storage
    from google.oauth2 import service_account

    if credentials_json and os.path.exists(credentials_json):
        creds = service_account.Credentials.from_service_account_file(credentials_json)
        return storage.Client(credentials=creds, project=creds.project_id)
    return storage.Client()


class GCSStorage:
    """Pushes a form photo — already on local disk via LocalStorage.save()
    — up to GCS, and hands back signed URLs for serving it. FormSubmission
    stores the resulting "gcs:<blob path>" string directly in image_path, so
    a GCS-backed submission is told apart from a local one by that prefix
    alone, with no schema migration needed.
    """

    PREFIX = "gcs:"

    def __init__(self, bucket_name: str, credentials_json: str | None):
        self.bucket_name = bucket_name
        self.credentials_json = credentials_json

    def upload(self, local_path: str, station_id, form_type: str) -> str:
        client = _gcs_client(self.credentials_json)
        bucket = client.bucket(self.bucket_name)
        ext = os.path.splitext(local_path)[1] or ".jpg"
        blob_path = f"submissions/{station_id}/{form_type}/{uuid.uuid4()}{ext}"
        bucket.blob(blob_path).upload_from_filename(local_path)
        return f"{self.PREFIX}{blob_path}"

    def signed_url(self, image_path: str, expiry_minutes: int = 60) -> str:
        blob_path = image_path[len(self.PREFIX):]
        client = _gcs_client(self.credentials_json)
        return client.bucket(self.bucket_name).blob(blob_path).generate_signed_url(
            expiration=timedelta(minutes=expiry_minutes)
        )

    def delete(self, image_path: str):
        blob_path = image_path[len(self.PREFIX):]
        client = _gcs_client(self.credentials_json)
        try:
            client.bucket(self.bucket_name).blob(blob_path).delete()
        except Exception:
            pass

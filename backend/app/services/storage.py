"""Image storage abstraction.

Local filesystem for development; swap for Google Cloud Storage in
production (write bytes to a bucket, return the blob name instead of a path,
serve via signed URLs — see docs/DEPLOYMENT.md).
"""

import hashlib
import os
import uuid


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


class GCSStorage:
    """Persists a validated submission's image to GCS. Lazy-imports
    google-cloud-storage so importing this module never requires the
    package unless GCS is actually configured (STORAGE_BACKEND=gcs) —
    keeps local dev/tests working without installing it."""

    def __init__(self, bucket_name: str):
        from google.cloud import storage as gcs_storage
        self._bucket = gcs_storage.Client().bucket(bucket_name)

    def upload(self, local_path: str, sha256: str) -> str:
        """Object name is the sha256 (already computed by LocalStorage.save)
        plus the original extension — deterministic, so re-uploading
        identical bytes just overwrites with the same content."""
        ext = os.path.splitext(local_path)[1]
        object_name = f"{sha256}{ext}"
        blob = self._bucket.blob(object_name)
        blob.upload_from_filename(local_path)
        return object_name

    def download_bytes(self, object_name: str) -> bytes:
        return self._bucket.blob(object_name).download_as_bytes()

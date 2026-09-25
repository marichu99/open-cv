"""Image storage abstraction.

Local filesystem for development; swap for Google Cloud Storage in
production (write bytes to a bucket, return the blob name instead of a path,
serve via signed URLs — see docs/DEPLOYMENT.md).
"""

import hashlib
import io
import os
import uuid

from PIL import Image, ImageOps


def _strip_exif(data: bytes) -> bytes:
    """Re-encodes image bytes with all EXIF metadata removed before
    anything is persisted. A phone photo's EXIF commonly embeds GPS
    coordinates of exactly where it was taken (plus device make/model,
    capture timestamp) — this app has no purpose for that and no business
    retaining it; storing it unstripped is real, incidentally-collected
    sensitive personal data with no lawful basis behind it (see the ODPC
    registration's sensitive-data disclosure this was written to close).

    exif_transpose() bakes the EXIF orientation tag into actual pixel
    rotation first — a portrait phone photo would otherwise end up sideways
    once the tag that would have corrected it is gone.

    Falls back to the original bytes if Pillow can't decode them (e.g. a
    corrupt upload) — that's not this function's problem to solve,
    downstream (looks_blank, extraction) already handles an unreadable
    image without this needing to guess at it."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or "JPEG"
            img = ImageOps.exif_transpose(img)
            if fmt.upper() == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format=fmt)
            return buf.getvalue()
    except Exception:
        return data


class LocalStorage:
    def __init__(self, upload_dir: str):
        self.upload_dir = upload_dir
        os.makedirs(self.upload_dir, exist_ok=True)

    def save(self, file_storage) -> tuple[str, str]:
        """Persists an uploaded file, returns (absolute_path, sha256_hex).

        Absolute, because Flask's send_file() resolves relative paths against
        app.root_path, not the process CWD — storing a relative path here
        looks fine until the image is served back and 404s.

        Every upload passes through here before it's ever written to disk
        or pushed to GCS (see GCSStorage.upload below, which just uploads
        whatever LocalStorage already wrote) — the one place to strip EXIF
        so it's gone regardless of which storage backend ends up serving
        the image.
        """
        ext = os.path.splitext(file_storage.filename or "")[1].lower() or ".jpg"
        name = f"{uuid.uuid4()}{ext}"
        path = os.path.abspath(os.path.join(self.upload_dir, name))

        file_storage.stream.seek(0)
        data = _strip_exif(file_storage.read())
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

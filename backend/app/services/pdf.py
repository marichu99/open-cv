"""PDF -> image conversion for the upload pipeline.

Agents (and bulk-ingest jobs pulling scanned forms straight from the IEBC
portal) sometimes have a Form 34A as a PDF rather than a phone photo.
Rendering the first page to a PNG here lets it enter the exact same
storage/extraction path as a photo upload — nothing downstream needs to
know the submission originated as a PDF. 150 DPI matches pdf_to_images.py
at the repo root, so production uploads and training-data prep produce the
same kind of image the CV model will eventually be trained/run on.
"""

import io

import fitz  # PyMuPDF
from werkzeug.datastructures import FileStorage

PDF_DPI = 150


def is_pdf(file_storage: FileStorage) -> bool:
    filename = (file_storage.filename or "").lower()
    if filename.endswith(".pdf"):
        return True
    return (file_storage.mimetype or "").lower() == "application/pdf"


def pdf_first_page_to_image(file_storage: FileStorage) -> FileStorage:
    """Renders the first page of a PDF upload to a PNG, returned as a
    FileStorage so it can be handed to LocalStorage.save() / the extraction
    service exactly like a photo upload. Multi-page PDFs only use page 1 —
    Form 34A is a single results page per polling station."""
    file_storage.stream.seek(0)
    pdf_bytes = file_storage.read()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not read PDF: {exc}") from exc

    try:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        pix = doc[0].get_pixmap(dpi=PDF_DPI)
        png_bytes = pix.tobytes("png")
    finally:
        doc.close()

    base_name = (file_storage.filename or "form").rsplit(".", 1)[0]
    return FileStorage(
        stream=io.BytesIO(png_bytes),
        filename=f"{base_name}.png",
        content_type="image/png",
    )

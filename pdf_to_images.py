import fitz  # pymupdf
import os
from pathlib import Path

SOURCE_DIR = "/home/mabera/personal/FORM34A"
OUTPUT_DIR = "/home/mabera/personal/FORM34A_images"


def convert_pdfs_to_images(source_dir: str = SOURCE_DIR, output_dir: str = OUTPUT_DIR, dpi: int = 150) -> None:
    pdf_files = list(Path(source_dir).rglob("*.pdf"))
    total = len(pdf_files)

    if total == 0:
        print(f"No PDFs found in {source_dir}")
        return

    print(f"Found {total} PDF(s). Converting at {dpi} DPI...")
    os.makedirs(output_dir, exist_ok=True)

    for idx, pdf_path in enumerate(pdf_files, 1):
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=dpi)
                # Flatten the nested path into a unique filename
                rel = pdf_path.relative_to(source_dir)
                name = str(rel).replace("/", "_").replace(".pdf", f"_p{page_num}.png")
                out_path = os.path.join(output_dir, name)
                pix.save(out_path)
            doc.close()
            print(f"[{idx}/{total}] Converted: {pdf_path.name} ({len(doc)} page(s))")
        except Exception as e:
            print(f"[{idx}/{total}] ERROR on {pdf_path}: {e}")

    print(f"\nDone. Images saved to: {output_dir}")


if __name__ == "__main__":
    convert_pdfs_to_images()

import cv2
from pathlib import Path

IMAGES_DIR = "/home/mabera/personal/FORM34A_images"
CLASS_ID = 0
FALLBACK_MARGIN = 0.01  # used if content-bound detection fails


def label_image(img_path: Path) -> tuple[float, float, float, float]:
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    h, w = img.shape

    # Non-white pixels = the printed form content (vs. the scan/render background).
    _, thresh = cv2.threshold(img, 245, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        m = FALLBACK_MARGIN
        x0, y0, x1, y1 = w * m, h * m, w * (1 - m), h * (1 - m)
    else:
        x0, y0, x1, y1 = w, h, 0, 0
        for c in contours:
            if cv2.contourArea(c) < (w * h * 0.001):
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            x0, y0 = min(x0, x), min(y0, y)
            x1, y1 = max(x1, x + cw), max(y1, y + ch)
        if x1 <= x0 or y1 <= y0:
            m = FALLBACK_MARGIN
            x0, y0, x1, y1 = w * m, h * m, w * (1 - m), h * (1 - m)

    x_center = ((x0 + x1) / 2) / w
    y_center = ((y0 + y1) / 2) / h
    box_w = (x1 - x0) / w
    box_h = (y1 - y0) / h
    return x_center, y_center, box_w, box_h


def main() -> None:
    images = sorted(Path(IMAGES_DIR).glob("*.png"))
    print(f"Found {len(images)} images. Auto-labeling class '{CLASS_ID}' (form34a)...")

    for idx, img_path in enumerate(images, 1):
        xc, yc, bw, bh = label_image(img_path)
        label_path = img_path.with_suffix(".txt")
        with open(label_path, "w") as f:
            f.write(f"{CLASS_ID} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")
        if idx % 50 == 0 or idx == len(images):
            print(f"[{idx}/{len(images)}] labeled")

    print("Done. Labels written next to each image as .txt (YOLO format).")


if __name__ == "__main__":
    main()

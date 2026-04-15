import os
import shutil
import random
from pathlib import Path

IMAGES_DIR = "/home/mabera/personal/FORM34A_images"
DATASET_DIR = "/home/mabera/personal/open-cv/dataset"
TRAIN_RATIO = 0.8
RANDOM_SEED = 42


def split_dataset(
    images_dir: str = IMAGES_DIR,
    dataset_dir: str = DATASET_DIR,
    train_ratio: float = TRAIN_RATIO,
) -> None:
    images = list(Path(images_dir).glob("*.png"))

    if not images:
        print(f"No PNG images found in {images_dir}. Run pdf_to_images.py first.")
        return

    # Only include images that have a matching label file
    annotated = [img for img in images if img.with_suffix(".txt").exists()]
    unannotated = len(images) - len(annotated)

    if unannotated > 0:
        print(f"Warning: {unannotated} image(s) have no label file and will be skipped.")

    if not annotated:
        print("No annotated images found. Annotate images with LabelImg first.")
        return

    random.seed(RANDOM_SEED)
    random.shuffle(annotated)
    split_idx = int(len(annotated) * train_ratio)
    train_files = annotated[:split_idx]
    val_files = annotated[split_idx:]

    for split_name, files in [("train", train_files), ("val", val_files)]:
        img_out = Path(dataset_dir) / "images" / split_name
        lbl_out = Path(dataset_dir) / "labels" / split_name
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for img_path in files:
            shutil.copy(img_path, img_out / img_path.name)
            label_path = img_path.with_suffix(".txt")
            shutil.copy(label_path, lbl_out / label_path.name)

    print(f"Dataset split complete:")
    print(f"  Train: {len(train_files)} images")
    print(f"  Val:   {len(val_files)} images")
    print(f"  Saved to: {dataset_dir}")

    _write_data_yaml(dataset_dir)


def _write_data_yaml(dataset_dir: str) -> None:
    yaml_path = os.path.join(dataset_dir, "data.yaml")
    content = f"""path: {dataset_dir}
train: images/train
val: images/val

nc: 1
names: ["form34a"]
"""
    with open(yaml_path, "w") as f:
        f.write(content)
    print(f"  data.yaml written to: {yaml_path}")


if __name__ == "__main__":
    split_dataset()

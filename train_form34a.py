from ultralytics import YOLO

DATASET_YAML = "dataset/data.yaml"
BASE_MODEL = "yolov8n.pt"


def train() -> None:
    model = YOLO(BASE_MODEL)

    model.train(
        data=DATASET_YAML,
        epochs=50,
        imgsz=640,
        batch=8,
        name="form34a_detector",
        project="runs/train",
    )

    print("\nTraining complete.")
    print("Best weights saved to: runs/train/form34a_detector/weights/best.pt")


if __name__ == "__main__":
    train()

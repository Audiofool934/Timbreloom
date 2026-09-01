import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import MODEL_ID, MODEL_SOURCE, get_model


def main() -> None:
    print(f"Preparing {MODEL_ID} from {MODEL_SOURCE}")
    model = get_model()
    print(f"Ready at {model.sample_rate} Hz")


if __name__ == "__main__":
    main()

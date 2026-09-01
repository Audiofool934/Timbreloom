from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import RUNTIME_DIR, _run_generation


REFERENCE_TEXT = "This is a clean reference recording for a local voice cloning test."
TARGET_TEXT = "The local voice cloning studio is ready for your recording."


def main() -> None:
    say = shutil.which("say")
    if say is None:
        raise RuntimeError("The macOS say command is required for the smoke test.")

    smoke_dir = RUNTIME_DIR / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    reference = smoke_dir / "reference.aiff"
    subprocess.run(
        [say, "-v", "Samantha", "-o", str(reference), REFERENCE_TEXT],
        check=True,
    )
    result = _run_generation(reference, REFERENCE_TEXT, TARGET_TEXT, "english")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Generated: {Path(result['audio_url']).name}")


if __name__ == "__main__":
    main()

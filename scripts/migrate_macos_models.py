"""Reuse existing local model weights outside the app without downloading or deleting sources."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from timbreloom.model_store import ModelStore
from macos_bundle import clone_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path,
                        default=Path.home() / "Library/Application Support/Timbreloom/models")
    args = parser.parse_args()
    source, destination = args.source.expanduser().resolve(), args.destination.expanduser().resolve()
    if source == destination:
        parser.error("The source and destination must differ")
    store = ModelStore(destination)
    imported = store.import_existing(source, copy_file=clone_file)
    print(json.dumps({"source": str(source), "destination": str(destination), "imported": imported,
                      "source_preserved": True, "network_used": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

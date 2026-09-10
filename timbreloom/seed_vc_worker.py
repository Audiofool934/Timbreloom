"""Launch the separate Seed-VC engine using read-only, bundled model assets.

Seed-VC is GPL-3.0 software; its unmodified source and license accompany the Mac bundle.
This entrypoint only adapts local model locations and does not change the engine source.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import sys


def prepare_config(template: Path, models: Path, destination: Path) -> Path:
    import yaml

    config = yaml.safe_load(template.read_text())
    parameters = config["model_params"]
    parameters["speech_tokenizer"]["name"] = str(models / "dependencies/whisper-small")
    parameters["vocoder"]["name"] = str(models / "dependencies/bigvgan")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(config, sort_keys=False))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-source", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args, engine_args = parser.parse_known_args()
    if engine_args and engine_args[0] == "--":
        engine_args = engine_args[1:]
    source = args.engine_source.resolve()
    models = args.models.resolve()
    config_index = engine_args.index("--config") + 1
    output = Path(engine_args[engine_args.index("--output") + 1])
    config = prepare_config(Path(engine_args[config_index]), models, output.parent / "seed-vc-config.yml")
    engine_args[config_index] = str(config)
    sys.path.insert(0, str(source))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import hf_utils

    def local_model(repo_id, model_filename="pytorch_model.bin", config_filename=None):
        if (repo_id, model_filename, config_filename) != ("funasr/campplus", "campplus_cn_common.bin", None):
            raise RuntimeError(f"The offline Seed-VC bundle does not include {repo_id}/{model_filename}")
        path = models / "dependencies/campplus/campplus_cn_common.bin"
        if not path.is_file():
            raise FileNotFoundError("The bundled CAMPPlus model is missing")
        return str(path)

    # The upstream loader otherwise writes a ./checkpoints cache inside the signed app.
    hf_utils.load_custom_model_from_hf = local_model
    sys.argv = [str(source / "inference.py"), *engine_args]
    runpy.run_path(str(source / "inference.py"), run_name="__main__")


if __name__ == "__main__":
    main()

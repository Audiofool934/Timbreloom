# Third-party software and model weights

The independently authored Timbreloom application and integration code is available under the MIT License.
Timbreloom also uses independently licensed upstream projects.
The Timbreloom license does not replace their licenses or grant rights to third-party model weights, input recordings, or voices.

## Seed-VC

The voice-conversion engine is [Seed-VC](https://github.com/Plachtaa/seed-vc), pinned to commit `51383efd921027683c89e5348211d93ff12ac2a8`.
Its [license at that revision](https://github.com/Plachtaa/seed-vc/blob/51383efd921027683c89e5348211d93ff12ac2a8/LICENSE) is GNU GPL version 3.
The source checkout is downloaded into the ignored `runtime/seed-vc/source` directory.
The Mac packaging workflow includes the pinned engine source and its license.
The host launches a separate process using command-line arguments and audio files.
Inside that process, `timbreloom/seed_vc_worker.py` imports Seed-VC helpers, replaces a model-loading function to use local files, and executes the engine with `runpy`.
This is tighter coupling than invoking an entirely unmodified external executable, so a process boundary alone is not treated as an exemption from GPL obligations.
The MIT grant applies to Timbreloom-authored code only.
If a distributed combination is a GPL-covered work, distribution must comply with GPL for that combination, while preserving the MIT notices on the Timbreloom-authored portions.
The original source files and license of Seed-VC are not relicensed under MIT.
See [Seed-VC integration](docs/seed-vc-integration.md) for the process boundary and model revisions.

## Other dependencies and model weights

The direct application dependencies are declared in `pyproject.toml` and resolved in `uv.lock`.
The isolated Seed-VC production dependencies are pinned in `packaging/seed-vc-runtime.lock`.
Models are identified by repository, revision, license information when available, file size, and checksum in `timbreloom/model_catalog.json`.
Model weights are downloaded separately and are not included in this source repository.
Consult each upstream repository and model card for the terms applicable to a particular component.

## Distributing a Mac application

A built Mac application contains more third-party components than this source repository, including Python, MLX, PyTorch, FFmpeg, and audio libraries.
The packaging scripts collect installed package metadata, upstream licenses, and corresponding source material into the application.
The app exposes these notices through its Help menu.
Anyone distributing a binary must retain the required notices and meet the applicable source-availability and redistribution terms of those components.
The source-repository license alone is not a substitute for those obligations.

# Mac production runtime inputs

The app contains two isolated Python runtimes because the current MLX and Seed-VC stacks require different dependency versions.
Weights remain separate and are downloaded only after the user selects a model.

`scripts/release_runtime.py` creates fresh temporary environments for every release build.
The main service uses the root `uv.lock` with `uv sync --locked --no-default-groups --no-editable`.
The Seed-VC service uses `seed-vc-runtime.lock`, generated from `scripts/seed-vc-requirements.txt`, with exact versions and distribution hashes.
The initial Seed-VC lock preserves the versions already validated in RC5 rather than upgrading transitive dependencies during packaging cleanup.
Builds require the existing Python interpreters and uv, but never copy packages from or modify either developer environment.
Dependency downloads are permitted during a build; inference remains offline after a model has been installed.

The portable interpreter is copied without its bootstrap site-packages, then populated only from the clean production environment.
Test-suite directories named `test` or `tests`, interpreter development tools, and interpreter build headers are removed from the staged copy.
Public runtime helpers such as `numpy.testing`, `unittest`, and package-level headers are retained to avoid breaking imports.
The package inventory rejects pytest, pip, lint tools, coverage tools, and other explicitly development-only distributions.
The packaged manifest records both lock hashes, installed package versions, and the paths and sizes omitted from the runtime.

Some upstream packages require components that also serve development use cases.
Torch on Python 3.12 declares setuptools as a dependency.
Seed-VC imports DAC, whose audio toolkit declares IPython, plotting, and TensorBoard dependencies.
These dependencies stay installed until the upstream import chain can be changed and verified as a separate task.
Removing them only by name would leave a broken or unsupported environment.
Third-party licenses and corresponding engine sources remain included.

To intentionally update the Seed-VC lock, review the resolver's version changes and run:

```bash
uv pip compile scripts/seed-vc-requirements.txt --python runtime/seed-vc/.venv/bin/python --generate-hashes --format requirements.txt --output-file packaging/seed-vc-runtime.lock
```

After a dependency or pruning change, validate the assembled runtime with actual Whisper, Qwen, and Seed-VC inference plus media exports.
Tests run from the development workspace against the installed or mounted app; pytest is never installed inside the app to run them.

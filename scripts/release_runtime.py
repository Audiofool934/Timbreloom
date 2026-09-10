"""Prepare locked production environments and omit development-only payloads."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEV_DISTRIBUTIONS = {
    "pip", "pytest", "pytest-asyncio", "pytest-cov", "pytest-xdist", "coverage",
    "black", "isort", "ruff", "mypy", "pre-commit", "httpx2",
}
TEST_DIRECTORIES = {"test", "tests"}
STDLIB_DEVELOPMENT = {"ensurepip", "idlelib", "turtledemo"}


def distributions(python: Path) -> list[dict]:
    script = (
        "import importlib.metadata as m,json;"
        "print(json.dumps(sorted([{'name':d.metadata['Name'],'version':d.version,"
        "'license':d.metadata.get('License-Expression') or d.metadata.get('License','')} "
        "for d in m.distributions()],key=lambda d:d['name'].lower())))"
    )
    return json.loads(subprocess.check_output([str(python), "-I", "-c", script], text=True))


def assert_production_packages(packages: list[dict]) -> None:
    normalized = [package["name"].lower().replace("_", "-") for package in packages]
    names = set(normalized)
    if len(names) != len(normalized):
        raise RuntimeError("Duplicate package metadata in production runtime")
    unwanted = sorted(names & DEV_DISTRIBUTIONS)
    if unwanted:
        raise RuntimeError(f"Development distributions in production runtime: {', '.join(unwanted)}")


@contextmanager
def production_environments():
    """Never install into, prune, or copy packages from the developer environments."""
    with tempfile.TemporaryDirectory(prefix="production-", dir=ROOT / "build") as temporary:
        stage = Path(temporary)
        main, seed = stage / "main", stage / "seed-vc"
        environment = os.environ.copy()
        environment.pop("VIRTUAL_ENV", None)
        environment["UV_PROJECT_ENVIRONMENT"] = str(main)
        environment["UV_PYTHON_DOWNLOADS"] = "never"
        subprocess.run(["uv", "sync", "--project", str(ROOT), "--locked", "--no-default-groups",
                        "--no-editable", "--python", str(ROOT / ".venv/bin/python")],
                       env=environment, cwd=ROOT, check=True)
        subprocess.run(["uv", "venv", "--python", str(ROOT / "runtime/seed-vc/.venv/bin/python"),
                        "--no-python-downloads", str(seed)], env=environment, cwd=ROOT, check=True)
        subprocess.run(["uv", "pip", "sync", "--python", str(seed / "bin/python"), "--require-hashes",
                        "--strict", str(ROOT / "packaging/seed-vc-runtime.lock")],
                       env=environment, cwd=ROOT, check=True)
        for runtime in (main, seed):
            subprocess.run(["uv", "pip", "check", "--python", str(runtime / "bin/python")],
                           cwd=ROOT, check=True)
            assert_production_packages(distributions(runtime / "bin/python"))
        yield {"main": main, "seed-vc": seed}


def prune_runtime(runtime: Path, version: str) -> dict:
    """Remove test suites and interpreter development tools only from a staged copy.

    Public library helpers such as numpy.testing and unittest remain available.
    Upstream runtime dependencies, including setuptools when required by Torch,
    are selected by the resolver rather than removed by a name heuristic.
    """
    standard = runtime / "lib" / f"python{version}"
    removed = []
    for directory, names, _ in os.walk(runtime):
        parent = Path(directory)
        for name in list(names):
            path = parent / name
            if name in TEST_DIRECTORIES or (parent == standard and name in STDLIB_DEVELOPMENT):
                size = sum(file.stat().st_size for file in path.rglob("*")
                           if file.is_file() and not file.is_symlink())
                removed.append({"path": path.relative_to(runtime).as_posix(), "bytes": size})
                shutil.rmtree(path)
                names.remove(name)
    # Extension headers and interpreter Makefiles are for building Python extensions.
    # Package-level headers remain intact for any libraries that use them at runtime.
    for path in [runtime / "include", *standard.glob("config-*")]:
        if path.is_dir():
            size = sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
            removed.append({"path": path.relative_to(runtime).as_posix(), "bytes": size})
            shutil.rmtree(path)
    leftovers = [path.relative_to(runtime).as_posix() for path in runtime.rglob("*")
                 if path.is_dir() and path.name in TEST_DIRECTORIES]
    if leftovers:
        raise RuntimeError(f"Test suites in production runtime: {leftovers}")
    return {"removed_bytes": sum(entry["bytes"] for entry in removed), "removed": removed}


def lock_provenance() -> dict:
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "uv.lock", ROOT / "packaging/seed-vc-runtime.lock")}

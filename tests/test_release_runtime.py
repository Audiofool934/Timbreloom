import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from release_runtime import assert_production_packages, prune_runtime


def test_release_rejects_development_distributions_but_keeps_runtime_dependencies():
    assert_production_packages([{"name": "numpy"}, {"name": "setuptools"}, {"name": "ipython"}])
    with pytest.raises(RuntimeError, match="pytest-asyncio"):
        assert_production_packages([{"name": "pytest_asyncio"}])
    with pytest.raises(RuntimeError, match="pip"):
        assert_production_packages([{"name": "pip"}])
    with pytest.raises(RuntimeError, match="Duplicate"):
        assert_production_packages([{"name": "setuptools"}, {"name": "setuptools"}])


def test_pruning_removes_suites_without_removing_public_helpers_or_model_data(tmp_path):
    files = [
        "lib/python3.12/site-packages/numpy/tests/test_numeric.py",
        "lib/python3.12/site-packages/numpy/testing/__init__.py",
        "lib/python3.12/site-packages/numpy/data/reference.npy",
        "lib/python3.12/site-packages/torch/tests/cpp/test.bin",
        "lib/python3.12/site-packages/torch/include/runtime.h",
        "lib/python3.12/site-packages/numpy-1.dist-info/LICENSE.txt",
        "lib/python3.12/unittest/mock.py",
        "lib/python3.12/ensurepip/_bundled/pip.whl",
        "lib/python3.12/idlelib/idle.py",
        "lib/python3.12/config-3.12/Makefile",
        "include/python3.12/Python.h",
    ]
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    report = prune_runtime(tmp_path, "3.12")
    for name in files:
        should_exist = any(part in name for part in ["/testing/", "/data/", "torch/include/", "dist-info/", "/unittest/"])
        assert (tmp_path / name).exists() == should_exist, name
    assert report["removed_bytes"] == 6 * len(b"fixture")
    assert prune_runtime(tmp_path, "3.12")["removed_bytes"] == 0

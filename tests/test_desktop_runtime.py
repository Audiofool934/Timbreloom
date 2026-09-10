import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

import app
from timbreloom.runtime_lock import DataDirectoryLock


def test_library_lock_excludes_second_writer_and_releases(tmp_path):
    with DataDirectoryLock(tmp_path):
        with pytest.raises(RuntimeError, match="已有 Timbreloom"):
            with DataDirectoryLock(tmp_path):
                pytest.fail("A second writer must not start")
    with DataDirectoryLock(tmp_path):
        pass


def test_light_health_and_runtime_do_not_walk_library(monkeypatch):
    def unexpected(*_):
        pytest.fail("Idle polling must not scan saved media")

    monkeypatch.setattr(app, "_list_voice_profiles", unexpected)
    monkeypatch.setattr(app._asr_service, "list_transcripts", unexpected)
    monkeypatch.setattr(app._dub_store, "list", unexpected)
    monkeypatch.setattr(app._vc_service, "list", unexpected)
    assert "saved_voices" not in app.health(library=False)
    assert app.runtime_status()["app"] == "timbreloom"


@pytest.mark.parametrize("name", ["_tts_jobs", "_asr_service", "_vc_service", "_dub_render_service", "_dub_export_service"])
def test_runtime_guards_queued_work_even_without_accelerator(monkeypatch, name):
    services = ["_tts_jobs", "_asr_service", "_vc_service", "_dub_render_service", "_dub_export_service"]
    monkeypatch.setattr(app, "_accelerator", SimpleNamespace(active=None))
    for service in services:
        monkeypatch.setattr(app, service, SimpleNamespace(has_active_jobs=lambda: False))
    assert app.runtime_status()["busy"] is False
    monkeypatch.setattr(app, name, SimpleNamespace(has_active_jobs=lambda: True))
    assert app.runtime_status()["busy"] is True


def test_startup_does_not_import_inference_or_cloud_sdk(tmp_path):
    env = {**os.environ, "TIMBRELOOM_DATA_DIR": str(tmp_path), "TIMBRELOOM_PRELOAD": "0"}
    result = subprocess.run([
        sys.executable, "-c",
        "import app, sys; app._tts_provider.unload(); "
        "assert 'mlx.core' not in sys.modules; "
        "assert 'numpy' not in sys.modules; "
        "assert 'mlx_audio' not in sys.modules; assert 'google.genai' not in sys.modules",
    # This is an import-isolation assertion, not a wall-clock performance budget.
    # A busy shared Mac has been observed taking 22 seconds in ordinary SDK imports.
    ], cwd=Path(app.APP_ROOT), env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_desktop_supervisor_starts_and_cleans_its_process_group(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "TIMBRELOOM_DATA_DIR": str(tmp_path), "TIMBRELOOM_PRELOAD": "0"}
    log = (tmp_path / "test.log").open("w")
    process = subprocess.Popen([
        sys.executable, "-m", "timbreloom.desktop_server", "--port", str(port), "--parent", str(os.getpid()),
    ], cwd=Path(app.APP_ROOT), env=env, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 60
        state = None
        while time.monotonic() < deadline:
            assert process.poll() is None, (tmp_path / "test.log").read_text()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/runtime", timeout=.3) as response:
                    state = json.load(response)
                    break
            except OSError:
                time.sleep(.1)
        assert state and state["data_root"] == str(tmp_path.resolve())
        assert state["busy"] is False
        assert os.getpgid(state["pid"]) == process.pid
        process.terminate()
        process.wait(timeout=8)
        with pytest.raises(ProcessLookupError):
            os.kill(state["pid"], 0)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        log.close()

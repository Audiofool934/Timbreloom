import hashlib
import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from timbreloom.model_store import ModelStore, default_model_root


def catalog_for(contents):
    return {key: {"id": key, "directory": key, "name": key, "purpose": key,
                  "description": key, "sources": [], "bytes": len(content),
                  "files": [{"path": "weights.bin", "size": len(content),
                             "sha256": hashlib.sha256(content).hexdigest(),
                             "repository": f"test/{key}", "revision": "a" * 40,
                             "filename": "weights.bin"}]}
            for key, content in contents.items()}


def wait_idle(store):
    deadline = time.monotonic() + 5
    while store.has_active_jobs() and time.monotonic() < deadline:
        time.sleep(.01)
    assert not store.has_active_jobs()
    return store.snapshot()["models"][0]


def test_fresh_status_has_no_network_or_filesystem_side_effects(tmp_path):
    requests = []
    root = tmp_path / "not-created"
    store = ModelStore(root, catalog=catalog_for({"qwen": b"a", "whisper": b"b"}),
                       transport=httpx.MockTransport(lambda request: requests.append(request)))
    assert [m["state"] for m in store.snapshot()["models"]] == ["missing", "missing"]
    assert not store.ready("qwen")
    assert not requests and not root.exists()
    store.close()


def test_pinned_moonshine_download_uses_cdn_and_verifies_hash(tmp_path):
    content = b"pinned Moonshine model"
    catalog = catalog_for({"moonshine-en": content})
    artifact = catalog["moonshine-en"]["files"][0]
    artifact["download_url"] = "https://download.moonshine.ai/model/small-streaming-en/quantized_26_08_21/encoder.ort"
    requests = []
    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200, content=content if len(requests) > 1 else b"x" * len(content))
    store = ModelStore(tmp_path, catalog=catalog, transport=httpx.MockTransport(respond))
    try:
        store.start("moonshine-en")
        assert wait_idle(store)["state"] == "error" and not store.ready("moonshine-en")
        store.start("moonshine-en")
        assert wait_idle(store)["state"] == "ready"
        assert requests == [artifact["download_url"]] * 2
    finally:
        store.close()


def test_only_explicitly_selected_model_downloads_and_activates(tmp_path):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=b"chosen")
    store = ModelStore(tmp_path, catalog=catalog_for({"qwen": b"chosen", "whisper": b"other"}),
                       transport=httpx.MockTransport(respond))
    try:
        store.start("qwen")
        assert wait_idle(store)["state"] == "ready"
        assert store.ready("qwen") and not store.ready("whisper")
        assert len(requests) == 1 and "/test/qwen/resolve/" in str(requests[0].url)
        assert not (tmp_path / "whisper").exists()
        store.start("qwen")
        assert len(requests) == 1
    finally:
        store.close()


@pytest.mark.parametrize("honor_range", [True, False])
def test_restart_resumes_partial_or_replaces_ignored_range(tmp_path, honor_range):
    content = b"known model contents"
    partial = tmp_path / ".downloads/qwen/files/weights.bin.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(content[:5])
    (partial.parent.parent / "status.json").write_text(json.dumps({"state": "downloading", "downloaded_bytes": 5}))
    requests = []
    def respond(request):
        requests.append(request)
        assert request.headers["Range"] == "bytes=5-"
        if honor_range:
            return httpx.Response(206, content=content[5:], headers={"Content-Range": f"bytes 5-{len(content)-1}/{len(content)}"})
        return httpx.Response(200, content=content)
    store = ModelStore(tmp_path, catalog=catalog_for({"qwen": content}), transport=httpx.MockTransport(respond))
    try:
        assert store.snapshot()["models"][0]["state"] == "paused"
        assert not requests and not store.ready("qwen")
        store.start("qwen")
        assert wait_idle(store)["state"] == "ready"
        assert (tmp_path / "qwen/weights.bin").read_bytes() == content
    finally:
        store.close()


def test_pause_preserves_bytes_releases_lease_and_requires_manual_resume(tmp_path):
    chunk = b"x" * (256 * 1024)
    content = chunk * 4
    first_read = threading.Event()
    release = threading.Event()
    class Slow(httpx.SyncByteStream):
        def __iter__(self):
            yield chunk
            first_read.set()
            release.wait(3)
            yield content[len(chunk):]
    catalog = catalog_for({"qwen": content})
    store = ModelStore(tmp_path, catalog=catalog, transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Slow())))
    second = ModelStore(tmp_path, catalog=catalog)
    try:
        store.start("qwen")
        assert first_read.wait(2)
        assert not store.ready("qwen")
        with pytest.raises(RuntimeError, match="Another"):
            second.start("qwen")
        store.pause("qwen")
        release.set()
        assert wait_idle(store)["state"] == "paused"
        assert (tmp_path / ".downloads/qwen/files/weights.bin.partial").stat().st_size == len(chunk)
        assert second.snapshot()["models"][0]["state"] == "paused"
        assert not second.has_active_jobs()
        second.transport = httpx.MockTransport(lambda request: httpx.Response(206, content=content[len(chunk):],
            headers={"Content-Range": f"bytes {len(chunk)}-{len(content)-1}/{len(content)}"}))
        second.start("qwen")
        assert wait_idle(second)["state"] == "ready"
    finally:
        release.set()
        store.close()
        second.close()


@pytest.mark.parametrize("mode", ["bad_hash", "short", "bad_range", "offline"])
def test_failed_transfer_cannot_activate_and_retry_works(tmp_path, mode):
    content = b"correct model"
    def respond(request):
        if mode == "offline":
            raise httpx.ConnectError("offline", request=request)
        if mode == "bad_range":
            return httpx.Response(206, content=content, headers={"Content-Range": "bytes 1-13/14"})
        return httpx.Response(200, content=b"x" * len(content) if mode == "bad_hash" else content[:3])
    store = ModelStore(tmp_path, catalog=catalog_for({"qwen": content}), transport=httpx.MockTransport(respond))
    try:
        store.start("qwen")
        assert wait_idle(store)["state"] == "error"
        assert not store.ready("qwen") and not (tmp_path / "qwen").exists()
        store.transport = httpx.MockTransport(lambda _: httpx.Response(200, content=content))
        store.start("qwen")
        assert wait_idle(store)["state"] == "ready"
    finally:
        store.close()


def test_import_validates_hash_and_preserves_source_and_complete_destination(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    original = source / "qwen/weights.bin"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"wrong")
    store = ModelStore(destination, catalog=catalog_for({"qwen": b"right"}))
    with pytest.raises(ValueError, match="checksum"):
        store.import_existing(source)
    assert not store.ready("qwen")
    original.write_bytes(b"right")
    assert store.import_existing(source) == ["qwen"]
    assert original.read_bytes() == b"right"
    assert store.import_existing(source) == []
    assert store.ready("qwen")


def test_embedded_default_keeps_weights_outside_app_and_override_is_supported(tmp_path, monkeypatch):
    monkeypatch.delenv("TIMBRELOOM_MODELS_DIR", raising=False)
    monkeypatch.setenv("TIMBRELOOM_EMBEDDED", "1")
    assert default_model_root(tmp_path / "app", tmp_path / "support/data") == tmp_path / "support/models"
    monkeypatch.setenv("TIMBRELOOM_MODELS_DIR", str(tmp_path / "custom"))
    assert default_model_root(tmp_path / "app", tmp_path / "support/data") == tmp_path / "custom"


def test_api_missing_models_is_reachable_and_inference_does_not_start_downloads(tmp_path, monkeypatch):
    import app
    from fastapi.testclient import TestClient
    from timbreloom.model_store import model_catalog
    requests = []
    store = ModelStore(tmp_path / "empty", catalog=model_catalog(),
                       transport=httpx.MockTransport(lambda request: requests.append(request)))
    monkeypatch.setattr(app, "_model_store", store)
    client = TestClient(app.app, base_url="http://127.0.0.1")
    assert client.get("/api/health").json()["ok"]
    assert client.get("/api/health").json()["model_status"] == "missing"
    assert all(not model["ready"] for model in client.get("/api/models").json()["models"])
    response = client.post("/api/asr/jobs", files={"media": ("test.wav", b"unused", "audio/wav")})
    assert response.status_code == 409 and "Download" in response.json()["detail"]
    assert client.post("/api/models/unknown/download").status_code == 404
    assert not requests and not store.root.exists()
    store.close()

import httpx
import pytest

import app
from scripts.e2e_v1 import check_service


def configured_health():
    health = app.health()
    # The protocol check must be testable without installing model weights.
    for provider in health["providers"]:
        provider["configured"] = True
    return health


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.3-rc.1"])
def test_preflight_accepts_compatible_releases_without_starting_model(version):
    health = configured_health()
    health["version"] = version

    def handle(request):
        assert request.method == "GET"
        return httpx.Response(
            200, json=health if request.url.path == "/api/health" else app.app.openapi()
        )

    with httpx.Client(
        transport=httpx.MockTransport(handle), base_url="http://testserver"
    ) as client:
        assert check_service(client)["version"] == version


@pytest.mark.parametrize("defect", ["version", "route", "provider", "title"])
def test_preflight_rejects_incompatible_services(defect):
    import copy

    health = copy.deepcopy(configured_health())
    schema = copy.deepcopy(app.app.openapi())
    if defect == "version":
        health["version"] = "2.0.0"
    elif defect == "route":
        del schema["paths"]["/api/dub/projects/{project_id}/export-jobs"]
    elif defect == "title":
        schema["info"]["title"] = "Another application"
    else:
        health["providers"] = []

    def handle(request):
        assert request.method == "GET"
        return httpx.Response(
            200, json=health if request.url.path == "/api/health" else schema
        )

    with httpx.Client(
        transport=httpx.MockTransport(handle), base_url="http://testserver"
    ) as client:
        with pytest.raises(RuntimeError):
            check_service(client)

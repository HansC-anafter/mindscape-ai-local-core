import json
from pathlib import Path

import pytest
import yaml


def _repo_root() -> Path | None:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    return None


def _load_compose() -> dict:
    repo_root = _repo_root()
    if repo_root is None:
        pytest.skip("Repository root files are not mounted in this container")
    return yaml.safe_load((repo_root / "docker-compose.yml").read_text(encoding="utf-8"))


def _load_service_seed() -> dict:
    repo_root = _repo_root()
    if repo_root is None:
        pytest.skip("Repository root files are not mounted in this container")
    seed_path = repo_root / "config/service-endpoints.seed.json"
    return json.loads(seed_path.read_text(encoding="utf-8"))


def test_frontend_and_backend_control_share_control_plane_profile():
    compose = _load_compose()
    services = compose["services"]

    assert services["backend-control"]["profiles"] == ["control-plane"]
    assert services["frontend"]["profiles"] == ["control-plane"]
    assert "backend-control" in services["frontend"]["depends_on"]
    assert "backend" not in services["frontend"]["depends_on"]


def test_frontend_control_plane_dependency_matches_seed_contract():
    compose = _load_compose()
    seed = _load_service_seed()

    frontend_dependencies = compose["services"]["frontend"]["depends_on"]
    control_api_internal_urls = {
        endpoint["url"]
        for endpoint in seed["endpoints"]
        if endpoint.get("service_id") == "local_core.control_api"
        and endpoint.get("audience") in {"container_internal", "server_internal"}
    }

    assert frontend_dependencies["backend-control"]["condition"] == "service_healthy"
    assert control_api_internal_urls == {"http://backend-control:8210"}

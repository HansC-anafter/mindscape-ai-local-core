import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
RUN_BACKEND_SERVER_SCRIPT = BACKEND_ROOT / "scripts" / "run_backend_server.sh"
DOCKER_COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.core.backend_runtime_mode import (  # noqa: E402
    get_uvicorn_reload_excludes,
    should_enable_capability_reload_watch,
)


def test_control_plane_does_not_watch_capability_tree_by_default(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "control")
    monkeypatch.delenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", raising=False)
    monkeypatch.delenv("LOCAL_CORE_DISABLE_CAPABILITY_RELOAD_WATCH", raising=False)

    assert should_enable_capability_reload_watch() is False


def test_control_plane_uvicorn_reload_excludes_installed_capability_tree_by_default(
    monkeypatch, tmp_path
):
    app_root = tmp_path / "app"
    capabilities_dir = app_root / "capabilities"
    staging_dir = app_root / ".capability-install-staging"
    capabilities_dir.mkdir(parents=True)
    staging_dir.mkdir(parents=True)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "control")
    monkeypatch.delenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", raising=False)
    monkeypatch.delenv("LOCAL_CORE_DISABLE_CAPABILITY_RELOAD_WATCH", raising=False)
    monkeypatch.chdir(tmp_path)

    excludes = get_uvicorn_reload_excludes(app_root=app_root)

    assert str(capabilities_dir.relative_to(tmp_path)) in excludes
    assert f"{capabilities_dir.relative_to(tmp_path)}/**/*" in excludes
    assert str(capabilities_dir.resolve()) in excludes
    assert f"{capabilities_dir.resolve()}/**/*" in excludes
    assert str(staging_dir.relative_to(tmp_path)) in excludes
    assert f"{staging_dir.relative_to(tmp_path)}/**/*" in excludes
    assert str(staging_dir.resolve()) in excludes
    assert f"{staging_dir.resolve()}/**/*" in excludes


def test_explicit_capability_reload_watch_override_wins(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "control")
    monkeypatch.setenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", "true")

    assert should_enable_capability_reload_watch() is True


def test_explicit_capability_reload_watch_override_keeps_reload_excludes_empty(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "control")
    monkeypatch.setenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", "true")

    assert get_uvicorn_reload_excludes(app_root=tmp_path) == []


def test_auto_dev_backend_can_watch_capability_tree(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "auto")
    monkeypatch.delenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", raising=False)
    monkeypatch.delenv("LOCAL_CORE_DISABLE_CAPABILITY_RELOAD_WATCH", raising=False)

    assert should_enable_capability_reload_watch() is True


def test_backend_server_reload_excludes_installed_capability_tree_when_not_watched():
    source = RUN_BACKEND_SERVER_SCRIPT.read_text(encoding="utf-8")

    assert "--reload-exclude backend/app/capabilities" in source
    assert "--reload-exclude 'backend/app/capabilities/**/*'" in source
    assert "--reload-exclude /app/backend/app/capabilities" in source
    assert "--reload-exclude '/app/backend/app/capabilities/**/*'" in source
    assert "--reload-exclude backend/app/.capability-install-staging" in source
    assert "--reload-exclude 'backend/app/.capability-install-staging/**/*'" in source
    assert "--reload-exclude /app/backend/app/.capability-install-staging" in source
    assert "--reload-exclude '/app/backend/app/.capability-install-staging/**/*'" in source


def test_backend_control_compose_disables_uvicorn_reload():
    source = DOCKER_COMPOSE_FILE.read_text(encoding="utf-8")
    backend_control_block = source.split("  backend-control:", maxsplit=1)[1].split(
        "\n  frontend:",
        maxsplit=1,
    )[0]

    assert "- MINDSCAPE_BACKEND_ROLE=control" in backend_control_block
    assert "- MINDSCAPE_BACKEND_RELOAD=false" in backend_control_block

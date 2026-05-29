import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.core.backend_runtime_mode import (  # noqa: E402
    should_enable_capability_reload_watch,
)


def test_control_plane_does_not_watch_capability_tree_by_default(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "control")
    monkeypatch.delenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", raising=False)
    monkeypatch.delenv("LOCAL_CORE_DISABLE_CAPABILITY_RELOAD_WATCH", raising=False)

    assert should_enable_capability_reload_watch() is False


def test_explicit_capability_reload_watch_override_wins(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "control")
    monkeypatch.setenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", "true")

    assert should_enable_capability_reload_watch() is True


def test_auto_dev_backend_can_watch_capability_tree(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MINDSCAPE_BACKEND_RELOAD", "true")
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "auto")
    monkeypatch.delenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH", raising=False)
    monkeypatch.delenv("LOCAL_CORE_DISABLE_CAPABILITY_RELOAD_WATCH", raising=False)

    assert should_enable_capability_reload_watch() is True

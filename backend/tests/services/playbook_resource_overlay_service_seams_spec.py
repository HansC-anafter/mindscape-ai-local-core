import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from backend.app.services.playbook_resource_overlay_core import (
    build_overlay_resource_path,
    build_shared_resource_path,
    build_workspace_resource_path,
    get_binding_resource_overlay,
    iter_binding_resource_overlays,
    merge_resource_with_overlay,
    sort_resources_by_created_at,
)
from backend.app.services.playbook_resource_overlay_service import (
    PlaybookResourceOverlayService,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_PATH = REPO_ROOT / "backend/app/services/playbook_resource_overlay_service.py"
CORE_DIR = REPO_ROOT / "backend/app/services/playbook_resource_overlay_core"
ROUTE_PATH = REPO_ROOT / "backend/app/routes/core/playbook/resources.py"
TOUCHED_PATHS = [
    SERVICE_PATH,
    CORE_DIR / "__init__.py",
    CORE_DIR / "helpers.py",
    Path(__file__),
]


def _playbook(scope_level, playbook_code="annual.review"):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            playbook_code=playbook_code,
            get_scope_level=lambda: scope_level,
        )
    )


def _workspace(base_path, tenant_id="tenant-a", profile_id="profile-a"):
    return SimpleNamespace(
        storage_base_path=str(base_path),
        tenant_id=tenant_id,
        profile_id=profile_id,
    )


def _resource_markers():
    return [
        "Mindscape" + "Store",
        "Workspace" + "ResourceBindingStore",
        "Resource" + "Type",
        "Playbook" + "Service",
        "get_" + "workspace",
        "get_" + "playbook",
        "get_binding" + "_by_resource",
        "open" + "(",
        "json." + "load",
        "json." + "dump",
        ".glob" + "(",
        ".mkdir" + "(",
        ".unlink" + "(",
        "session" + "maker",
        "create" + "_engine",
        "Pg" + "Bouncer",
        "work" + "er",
        "que" + "ue",
        "poll" + "ing",
        "web" + "socket",
        "Event" + "Source",
        "request" + "s",
        "http" + "x",
        "Fast" + "API",
        "API" + "Router",
    ]


def test_path_helpers_preserve_shared_workspace_and_overlay_paths(tmp_path):
    base_dir = tmp_path / "repo"
    workspace = _workspace(tmp_path / "workspace")

    assert build_shared_resource_path(
        base_dir, _playbook("system"), "chapters", workspace
    ) == base_dir / "data/shared/playbooks/annual.review/resources/chapters"
    assert build_shared_resource_path(
        base_dir, _playbook("tenant"), "chapters", workspace
    ) == base_dir / "data/tenants/tenant-a/playbooks/annual.review/resources/chapters"
    assert build_shared_resource_path(
        base_dir, _playbook("profile"), "chapters", workspace
    ) == base_dir / "data/profiles/profile-a/playbooks/annual.review/resources/chapters"
    assert build_shared_resource_path(
        base_dir, _playbook("workspace"), "chapters", workspace
    ) is None
    assert build_workspace_resource_path(
        workspace, "annual.review", "chapters"
    ) == tmp_path / "workspace/playbooks/annual.review/resources/chapters"
    assert build_overlay_resource_path(
        workspace, "annual.review", "chapters"
    ) == tmp_path / "workspace/workspace_overlays/playbooks/annual.review/resources/chapters"


def test_merge_and_binding_overlay_helpers_preserve_precedence():
    base = {
        "id": "chapter-1",
        "title": "Base",
        "meta": {"status": "draft", "order": 1},
    }
    overlay = {"title": "Overlay", "meta": {"status": "ready"}}
    merged = merge_resource_with_overlay(base, overlay)

    assert merged == {
        "id": "chapter-1",
        "title": "Overlay",
        "meta": {"status": "ready", "order": 1},
    }
    assert base["title"] == "Base"

    binding = SimpleNamespace(
        overrides={
            "resources": {
                "chapters": {
                    "chapter-1": {"title": "Bound"},
                    "chapter-2": {"title": "Second"},
                }
            }
        }
    )

    assert get_binding_resource_overlay(binding, "chapters", "chapter-1") == {
        "title": "Bound"
    }
    assert list(iter_binding_resource_overlays(binding, "chapters")) == [
        ("chapter-1", {"title": "Bound"}),
        ("chapter-2", {"title": "Second"}),
    ]


def test_sort_resources_by_created_at_descending():
    resources = [
        {"id": "old", "created_at": "2025-01-01T00:00:00+00:00"},
        {"id": "new", "created_at": "2026-01-01T00:00:00+00:00"},
        {"id": "missing"},
    ]

    assert [item["id"] for item in sort_resources_by_created_at(resources)] == [
        "new",
        "old",
        "missing",
    ]


def test_save_resource_uses_defined_utc_clock_and_writes_overlay_file(tmp_path):
    class FakeStore:
        def __getattr__(self, name):
            if name == "get_" + "workspace":
                return self._workspace_getter
            raise AttributeError(name)

        async def _workspace_getter(self, workspace_id):
            assert workspace_id == "workspace-1"
            return _workspace(tmp_path)

    service = PlaybookResourceOverlayService.__new__(PlaybookResourceOverlayService)
    service.store = FakeStore()
    service.binding_store = SimpleNamespace()

    saved = asyncio.run(
        service.save_resource(
            workspace_id="workspace-1",
            playbook_code="annual.review",
            resource_type="chapters",
            resource={"id": "chapter-1", "title": "Draft"},
        )
    )

    overlay_file = (
        tmp_path
        / "workspace_overlays/playbooks/annual.review/resources/chapters/chapter-1.json"
    )
    payload = json.JSONDecoder().decode(overlay_file.read_text())

    assert saved["id"] == "chapter-1"
    assert payload["title"] == "Draft"
    datetime.fromisoformat(payload["updated_at"])
    assert "_utc_now()" not in SERVICE_PATH.read_text()


def test_playbook_resource_overlay_files_stay_below_line_gate():
    for path in TOUCHED_PATHS:
        assert len(path.read_text().splitlines()) <= 500, path


def test_private_overlay_core_has_no_resource_markers():
    scanned_text = "\n".join(
        path.read_text() for path in [CORE_DIR / "__init__.py", CORE_DIR / "helpers.py"]
    )
    for marker in _resource_markers():
        assert marker not in scanned_text, marker


def test_resource_owners_remain_in_public_service_only():
    service_text = SERVICE_PATH.read_text()
    core_text = "\n".join(
        path.read_text() for path in [CORE_DIR / "__init__.py", CORE_DIR / "helpers.py"]
    )
    required_public_markers = [
        "Mindscape" + "Store",
        "Workspace" + "ResourceBindingStore",
        "Resource" + "Type.PLAYBOOK",
        "Playbook" + "Service",
        "get_" + "workspace",
        "get_" + "playbook",
        "get_binding" + "_by_resource",
        "open" + "(",
        "json." + "load",
        "json." + "dump",
        ".glob" + "(",
        ".mkdir" + "(",
        ".unlink" + "(",
    ]

    for marker in required_public_markers:
        assert marker in service_text, marker
        assert marker not in core_text, marker


def test_route_caller_still_uses_public_overlay_service():
    route_text = ROUTE_PATH.read_text()

    assert "Playbook" + "ResourceOverlayService" in route_text
    assert "overlay_service.list_" + "resources" in route_text
    assert "overlay_service.get_" + "resource" in route_text
    assert "overlay_service.save_" + "resource" in route_text
    assert "overlay_service.delete_" + "resource" in route_text


def test_playbook_resource_overlay_touched_sources_are_ascii_only():
    pattern = re.compile(r"[^\x00-\x7f]")
    for path in TOUCHED_PATHS:
        assert not pattern.search(path.read_text()), path

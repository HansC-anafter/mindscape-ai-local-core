import asyncio
import importlib.util
import sys
import types
from pathlib import Path

from backend.app.models.object_runtime import ObjectMeetingAttachRequest, ObjectRef


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROUTE_DIR = REPO_ROOT / "backend" / "app" / "routes" / "core" / "workspace"
WORKSPACE_PACKAGE_NAME = "backend.app.routes.core.workspace"

if WORKSPACE_PACKAGE_NAME not in sys.modules:
    workspace_package = types.ModuleType(WORKSPACE_PACKAGE_NAME)
    workspace_package.__path__ = [str(WORKSPACE_ROUTE_DIR)]
    sys.modules[WORKSPACE_PACKAGE_NAME] = workspace_package

_MODULE_PATH = WORKSPACE_ROUTE_DIR / "object_runtime.py"
_SPEC = importlib.util.spec_from_file_location(
    "backend.app.routes.core.workspace.object_runtime_target_only_attach_test_module",
    _MODULE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
object_runtime_routes = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = object_runtime_routes
_SPEC.loader.exec_module(object_runtime_routes)


class _FakeRegistry:
    def get_entry(self, owner_pack: str, object_kind: str):
        if owner_pack != "performance_direction" or object_kind != "storyboard_scene":
            return None
        return {
            "owner_pack": owner_pack,
            "object_kind": object_kind,
            "display_name": "Storyboard Scene",
            "id_field": "scene_id",
            "supports": ["meeting"],
            "meeting_projection_capabilities": {"available": False},
            "materializer_capabilities": {"available": False},
        }


class _FakeMeetingSessionStore:
    def __init__(self):
        self.created = []
        self.updated = []

    def get_by_id(self, meeting_id: str):
        return None

    def create(self, session):
        self.created.append(session)
        return session

    def update(self, session):
        self.updated.append(session)
        return session


def test_target_only_attach_opens_role_bearing_meeting_context(monkeypatch):
    async def _workspace_exists(_workspace_id: str):
        return None

    store = _FakeMeetingSessionStore()
    target_ref = ObjectRef(
        uri="mindscape://performance_direction/storyboard_scene/sc_open",
        owner_pack="performance_direction",
        object_kind="storyboard_scene",
        object_id="sc_open",
        workspace_id="ws_demo",
    )

    monkeypatch.setattr(object_runtime_routes, "_ensure_workspace_exists", _workspace_exists)
    monkeypatch.setattr(object_runtime_routes, "_get_object_catalog_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(object_runtime_routes, "_get_meeting_session_store", lambda: store)

    response = asyncio.run(
        object_runtime_routes.attach_objects_to_meeting(
            ObjectMeetingAttachRequest(
                meeting_type="direction",
                entries=[{"role": "target", "ref": target_ref.model_dump()}],
                intent_summary="Open the target scene as the meeting context.",
                write_mode="proposal_only",
            ),
            workspace_id="ws_demo",
        )
    )

    assert response.status == "attached"
    assert response.target_ref == target_ref
    assert response.attachments[0].role == "target"
    assert response.attachments[0].ref == target_ref

    assert store.updated
    metadata = store.updated[0].metadata["addressable_object_layer"]
    assert metadata["target_ref"]["uri"] == target_ref.uri
    assert metadata["context_entries"][0]["role"] == "target"
    handoff_aol = metadata["handoff_in"]["metadata"]["addressable_object_layer"]
    assert handoff_aol["target_ref_uri"] == target_ref.uri
    assert handoff_aol["role_object_uris"]["target"] == [target_ref.uri]
    assert handoff_aol["source_object_uris"] == []

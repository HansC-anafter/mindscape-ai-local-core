import os
import sys
from unittest.mock import MagicMock

_repo_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


class StubMixin:
    """Minimal stubs for mixin testing."""

    def __init__(self):
        self.session = MagicMock()
        self.session.id = "sess-001"
        self.session.workspace_id = "ws-default"
        self.session.round_count = 1
        self.profile_id = "user-001"
        self.project_id = "proj-001"
        self.execution_launcher = None
        self.tasks_store = None
        self._events = []

    def _emit_event(self, event_type, payload=None):
        self._events.append({"type": event_type, "payload": payload})

    async def _land_action_item(self, item):
        item["landing_status"] = "task_created"
        item["task_id"] = f"task-{item.get('title', 'x')}"
        return item


def bind_fake_dispatch_phase(orchestrator):
    async def _fake_dispatch_phase(phase, action_item, _task_ir_id):
        if action_item.get("landing_status") == "policy_blocked":
            return {"status": "skipped", "reason": "policy_blocked"}
        workspace_id = (
            phase.target_workspace_id
            or action_item.get("target_workspace_id")
            or getattr(orchestrator.session, "workspace_id", "")
        )
        return {
            "status": "completed",
            "workspace_id": workspace_id,
            "result": {"workspace_id": workspace_id},
        }

    orchestrator._dispatch_phase = _fake_dispatch_phase
    return orchestrator

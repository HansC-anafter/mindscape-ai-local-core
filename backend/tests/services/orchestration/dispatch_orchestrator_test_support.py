"""Shared support for DispatchOrchestrator tests."""

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest


_DO_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "app",
    "services",
    "orchestration",
    "dispatch_orchestrator.py",
)
_DO_PATH = os.path.normpath(_DO_PATH)
_spec = importlib.util.spec_from_file_location("dispatch_orchestrator", _DO_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["dispatch_orchestrator"] = _mod
_spec.loader.exec_module(_mod)
DispatchOrchestrator = _mod.DispatchOrchestrator


@dataclass
class FakePhaseIR:
    id: str
    name: str
    description: str = ""
    status: str = "pending"
    preferred_engine: Optional[str] = None
    target_workspace_id: Optional[str] = None
    tool_name: Optional[str] = None
    input_params: Optional[dict] = None
    depends_on: Optional[List[str]] = None
    blocked_by: Optional[List[int]] = None
    latest_attempt_id: Optional[str] = None


@dataclass
class FakeTaskIR:
    task_id: str = "task-ir-1"
    phases: List[Any] = field(default_factory=list)


@dataclass
class FakeSession:
    id: str = "session-1"
    workspace_id: str = "ws-default"
    thread_id: str = "thread-1"
    metadata: Dict[str, Any] = field(default_factory=dict)
    agenda: List[str] = field(default_factory=list)


async def _noop_publish_activity(event_type: str, data: dict) -> None:
    del event_type, data


def make_orchestrator(**overrides: Any) -> Any:
    defaults: Dict[str, Any] = {
        "execution_launcher": None,
        "tasks_store": None,
        "session": FakeSession(),
        "profile_id": "user-1",
        "project_id": "proj-1",
    }
    defaults.update(overrides)
    orch = DispatchOrchestrator(**defaults)
    orch._publish_activity = _noop_publish_activity
    return orch


async def _fake_dispatch_phase(
    orchestrator: Any,
    phase: FakePhaseIR,
    action_item: Dict[str, Any],
    task_ir_id: str,
) -> Dict[str, Any]:
    attempt = orchestrator._create_attempt(phase, task_ir_id)
    target_ws = (
        phase.target_workspace_id
        or action_item.get("target_workspace_id")
        or getattr(orchestrator.session, "workspace_id", None)
        or ""
    )
    attempt.target_workspace_id = target_ws

    landing_status = action_item.get("landing_status", "")
    if landing_status in ("policy_blocked", "dispatch_error", "boundary_violation"):
        attempt.mark_skipped(f"pre_blocked:{landing_status}")
        return {"status": "skipped", "reason": landing_status}

    if phase.preferred_engine:
        engine = phase.preferred_engine
    elif phase.tool_name:
        engine = f"tool:{phase.tool_name}"
    else:
        engine = "agent:auto"

    attempt.mark_dispatched(
        engine=engine,
        playbook_code=orchestrator._extract_playbook_code(engine),
        target_workspace_id=target_ws,
    )
    result = {
        "phase_id": phase.id,
        "phase_name": phase.name,
        "workspace_id": target_ws,
    }
    attempt.mark_completed(result)
    action_item["landing_status"] = "planned"
    return {"status": "completed", "workspace_id": target_ws, "result": result}


def make_fake_dispatch_orchestrator(**overrides: Any) -> Any:
    orch = make_orchestrator(**overrides)

    async def fake_dispatch_phase(
        phase: FakePhaseIR,
        action_item: Dict[str, Any],
        task_ir_id: str,
    ) -> Dict[str, Any]:
        return await _fake_dispatch_phase(orch, phase, action_item, task_ir_id)

    orch._dispatch_phase = fake_dispatch_phase
    return orch


@pytest.fixture
def orchestrator():
    return make_fake_dispatch_orchestrator()

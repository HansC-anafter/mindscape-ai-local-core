"""Shared fakes for HandoffBundleService tests."""

from contextlib import contextmanager
from dataclasses import dataclass, field
import sys
import types
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import MagicMock

from backend.app.models.handoff import DeliverableSpec, HandoffIn
from backend.app.services.handoff_bundle_service import HandoffBundleService

SIGNING_KEY_FIXTURE = "fixture-service-signing-key-32!"


@dataclass
class FakeMeetingResult:
    session_id: str = "sess-test-001"
    minutes_md: str = "Test minutes"
    decision: str = "Approve the plan"
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    task_ir: Optional[Any] = None


@dataclass
class FakeCompileModules:
    meeting_engine_cls: MagicMock
    session_store: MagicMock
    meeting_session_cls: MagicMock
    task_ir_store: MagicMock
    compile_job_store: MagicMock
    mindscape_store: MagicMock
    execution_launcher: MagicMock
    build_execution_launcher: MagicMock
    is_active_session_fresh: MagicMock


def make_handoff_bundle(
    *,
    handoff_id: str = "h_hp_001",
    workspace_id: str = "ws_001",
    intent_summary: str = "Build landing page",
    goals: Optional[List[str]] = None,
):
    handoff = HandoffIn(
        handoff_id=handoff_id,
        workspace_id=workspace_id,
        intent_summary=intent_summary,
        goals=goals or ["responsive", "SEO"],
        deliverables=[DeliverableSpec(name="index.html", mime_type="text/html")],
    )
    return HandoffBundleService().package_handoff(
        handoff_in=handoff,
        source_device_id="dev_A",
        secret_key=SIGNING_KEY_FIXTURE,
    )


@contextmanager
def install_fake_compile_modules(
    *,
    meeting_engine_cls: Optional[MagicMock] = None,
    session_store: Optional[MagicMock] = None,
    meeting_session_cls: Optional[MagicMock] = None,
    task_ir_store: Optional[MagicMock] = None,
    compile_job_store: Optional[MagicMock] = None,
    mindscape_store: Optional[MagicMock] = None,
    execution_launcher: Optional[MagicMock] = None,
    is_active_session_fresh: bool = True,
) -> Iterator[FakeCompileModules]:
    """Install fake inline-import modules used by compile_handoff_in()."""

    meeting_engine_cls = meeting_engine_cls or MagicMock()
    session_store = session_store or MagicMock()
    meeting_session_cls = meeting_session_cls or MagicMock()
    task_ir_store = task_ir_store or MagicMock()
    compile_job_store = compile_job_store or MagicMock()
    mindscape_store = mindscape_store or MagicMock()
    execution_launcher = execution_launcher or MagicMock(name="execution_launcher")
    build_execution_launcher = MagicMock(return_value=execution_launcher)
    is_active_session_fresh_mock = MagicMock(return_value=is_active_session_fresh)

    mod_meeting = types.ModuleType("backend.app.services.orchestration.meeting")
    mod_meeting.MeetingEngine = meeting_engine_cls

    mod_session_store = types.ModuleType(
        "backend.app.services.stores.meeting_session_store"
    )
    mod_session_store.MeetingSessionStore = MagicMock(return_value=session_store)
    mod_session_store.is_active_session_fresh = is_active_session_fresh_mock

    mod_meeting_session = types.ModuleType("backend.app.models.meeting_session")
    mod_meeting_session.MeetingSession = meeting_session_cls

    mod_pg_ir = types.ModuleType("backend.app.services.stores.postgres.task_ir_store")
    mod_pg_ir.PostgresTaskIRStore = MagicMock(return_value=task_ir_store)

    mod_compile_job_store = types.ModuleType(
        "backend.app.services.stores.compile_job_store"
    )
    mod_compile_job_store.CompileJobStore = MagicMock(return_value=compile_job_store)

    mod_mindscape_store = types.ModuleType("backend.app.services.mindscape_store")
    mod_mindscape_store.MindscapeStore = MagicMock(return_value=mindscape_store)

    mod_pipeline_meeting = types.ModuleType(
        "backend.app.services.conversation.pipeline_meeting"
    )
    mod_pipeline_meeting.build_execution_launcher = build_execution_launcher

    target_modules = {
        "backend.app.services.orchestration.meeting": mod_meeting,
        "backend.app.services.stores.meeting_session_store": mod_session_store,
        "backend.app.models.meeting_session": mod_meeting_session,
        "backend.app.services.stores.postgres.task_ir_store": mod_pg_ir,
        "backend.app.services.stores.compile_job_store": mod_compile_job_store,
        "backend.app.services.mindscape_store": mod_mindscape_store,
        "backend.app.services.conversation.pipeline_meeting": mod_pipeline_meeting,
    }
    saved = {name: sys.modules.get(name) for name in target_modules}
    sys.modules.update(target_modules)
    try:
        yield FakeCompileModules(
            meeting_engine_cls=meeting_engine_cls,
            session_store=session_store,
            meeting_session_cls=meeting_session_cls,
            task_ir_store=task_ir_store,
            compile_job_store=compile_job_store,
            mindscape_store=mindscape_store,
            execution_launcher=execution_launcher,
            build_execution_launcher=build_execution_launcher,
            is_active_session_fresh=is_active_session_fresh_mock,
        )
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

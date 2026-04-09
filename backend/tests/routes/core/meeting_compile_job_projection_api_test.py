from pathlib import Path
import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from backend.app.models.compile_job import CompileJob
from backend.app.models.meeting_session import MeetingSession


BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _load_meeting_sessions_module():
    fake_store_package = types.ModuleType("backend.app.services.stores")
    fake_store_package.__path__ = []
    fake_compile_job_store_module = types.ModuleType(
        "backend.app.services.stores.compile_job_store"
    )
    fake_compile_job_store_module.CompileJobStore = object
    fake_meeting_session_store_module = types.ModuleType(
        "backend.app.services.stores.meeting_session_store"
    )
    fake_meeting_session_store_module.MeetingSessionStore = object
    sys.modules.setdefault("backend.app.services.stores", fake_store_package)
    sys.modules.setdefault(
        "backend.app.services.stores.compile_job_store",
        fake_compile_job_store_module,
    )
    sys.modules.setdefault(
        "backend.app.services.stores.meeting_session_store",
        fake_meeting_session_store_module,
    )

    fake_mindscape_store_module = types.ModuleType(
        "backend.app.services.mindscape_store"
    )
    fake_mindscape_store_module.MindscapeStore = object
    sys.modules.setdefault(
        "backend.app.services.mindscape_store",
        fake_mindscape_store_module,
    )

    module_path = BACKEND_ROOT / "app" / "routes" / "meeting_sessions.py"
    spec = importlib.util.spec_from_file_location(
        "meeting_sessions_compile_projection_test_module",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_project_stats_module():
    fake_store_package = types.ModuleType("backend.app.services.stores")
    fake_store_package.__path__ = []
    fake_compile_job_store_module = types.ModuleType(
        "backend.app.services.stores.compile_job_store"
    )
    fake_compile_job_store_module.CompileJobStore = object
    fake_meeting_session_store_module = types.ModuleType(
        "backend.app.services.stores.meeting_session_store"
    )
    fake_meeting_session_store_module.MeetingSessionStore = object
    sys.modules.setdefault("backend.app.services.stores", fake_store_package)
    sys.modules.setdefault(
        "backend.app.services.stores.compile_job_store",
        fake_compile_job_store_module,
    )
    sys.modules.setdefault(
        "backend.app.services.stores.meeting_session_store",
        fake_meeting_session_store_module,
    )

    fake_mindscape_store_module = types.ModuleType(
        "backend.app.services.mindscape_store"
    )
    fake_mindscape_store_module.MindscapeStore = object
    sys.modules.setdefault(
        "backend.app.services.mindscape_store",
        fake_mindscape_store_module,
    )

    fake_workspace_dependencies_module = types.ModuleType(
        "backend.app.routes.workspace_dependencies"
    )

    async def fake_get_workspace():
        return None

    def fake_get_store():
        return None

    fake_workspace_dependencies_module.get_workspace = fake_get_workspace
    fake_workspace_dependencies_module.get_store = fake_get_store
    sys.modules.setdefault(
        "backend.app.routes.workspace_dependencies",
        fake_workspace_dependencies_module,
    )

    fake_project_manager_module = types.ModuleType(
        "backend.app.services.project.project_manager"
    )
    fake_project_manager_module.ProjectManager = object
    sys.modules.setdefault(
        "backend.app.services.project.project_manager",
        fake_project_manager_module,
    )

    module_path = (
        BACKEND_ROOT
        / "features"
        / "workspace"
        / "projects"
        / "routes"
        / "stats.py"
    )
    spec = importlib.util.spec_from_file_location(
        "project_stats_compile_projection_test_module",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ASGIAsyncTestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def request(self, method, url, **kwargs):
        async def _request():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_request())

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


def _make_session() -> MeetingSession:
    session = MeetingSession.new(
        workspace_id="ws-compile-001",
        project_id="proj-compile-001",
        thread_id="thread-compile-001",
    )
    session.start()
    session.round_count = 2
    session.minutes_md = "compile summary"
    session.metadata["round_routing_prompt_mode_summary"] = {
        "total_decisions": 2,
        "sparse_count": 1,
        "compressed_count": 1,
        "fallback_count": 0,
        "adaptive_count": 1,
        "sparse_ratio": 0.5,
        "compressed_ratio": 0.5,
        "fallback_ratio": 0.0,
        "adaptive_ratio": 0.5,
        "health_status": "warning",
        "health_reason": "compression_pressure",
        "last_prompt_mode": "compressed_sparse",
        "last_prompt_role_id": "executor",
        "last_prompt_reason": "context_pressure",
        "last_round_number": 2,
        "last_recorded_at": session.started_at.isoformat(),
    }
    session.metadata["last_program_spec"] = {
        "workstreams": [
            {
                "id": "WS1",
                "name": "Series Bible",
                "description": "Draft the long-form series bible.",
                "eligible_engines": ["playbook:project_breakdown"],
            },
            {
                "id": "WS2",
                "name": "Storyboard Seeds",
                "description": "Draft storyboard seeds for arc one.",
                "eligible_engines": ["tool:storyboard.generate"],
            },
        ],
        "milestones": [{"id": "M1", "name": "Arc Gate", "depends_on_streams": ["WS1"]}],
        "dependency_graph": {"WS2": ["WS1"]},
        "target_outputs": ["series_bible", "storyboard_seed_pack"],
        "scale": "program",
    }
    session.metadata["last_program_spec_source"] = "executor_structured"
    session.metadata["last_program_spec_workstream_count"] = 2
    session.metadata["program_run_id"] = "program-run-001"
    session.metadata["program_run_source"] = "executor_structured"
    session.metadata["program_run_status"] = "open"
    session.metadata["program_run_recorded_at"] = session.started_at.isoformat()
    session.metadata["program_run_workstream_count"] = 2
    session.metadata["program_run_milestone_count"] = 1
    session.metadata["program_run_target_outputs"] = [
        "series_bible",
        "storyboard_seed_pack",
    ]
    session.metadata["program_run_cursor_state"] = {
        "remaining_work_count": 1,
        "completed_workstream_ids": ["WS1"],
        "remaining_workstream_ids": ["WS2"],
    }
    return session


def _make_compile_job(session_id: str) -> CompileJob:
    job = CompileJob.new(
        workspace_id="ws-compile-001",
        project_id="proj-compile-001",
        thread_id="thread-compile-001",
        profile_id="profile-compile-001",
        session_id=session_id,
        metadata={
            "entry_point": "compile",
            "_internal_recovery_context": {"handoff_in": {"handoff_id": "hidden"}},
        },
    )
    job.mark_running(
        session_id=session_id,
        metadata={"route_kind": "meeting"},
    )
    return job


def test_meeting_sessions_endpoints_include_compile_job_summary(monkeypatch):
    module = _load_meeting_sessions_module()
    session = _make_session()
    job = _make_compile_job(session.id)
    compile_job_calls = []

    class FakeMeetingSessionStore:
        def get_by_id(self, session_id):
            if session_id == session.id:
                return session
            return None

        def list_by_workspace(self, workspace_id, project_id=None, limit=20, offset=0):
            assert workspace_id == session.workspace_id
            assert project_id == session.project_id
            return [session]

    class FakeCompileJobStore:
        def get_latest_for_session(self, session_id):
            compile_job_calls.append(session_id)
            if session_id == session.id:
                return job
            return None

    monkeypatch.setattr(module, "MeetingSessionStore", lambda: FakeMeetingSessionStore())
    monkeypatch.setattr(module, "CompileJobStore", lambda: FakeCompileJobStore())

    app = FastAPI()
    app.include_router(module.router)
    client = ASGIAsyncTestClient(app)

    list_response = client.get(
        f"/api/v1/workspaces/{session.workspace_id}/meeting-sessions",
        params={"project_id": session.project_id},
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["sessions"][0]["compile_job"]["id"] == job.id
    assert list_payload["sessions"][0]["compile_job"]["status"] == "running"
    assert "_internal_recovery_context" not in list_payload["sessions"][0]["compile_job"]["metadata"]
    assert list_payload["sessions"][0]["program_spec_summary"]["source"] == "executor_structured"
    assert list_payload["sessions"][0]["program_spec_summary"]["structured"] is True
    assert list_payload["sessions"][0]["program_spec_summary"]["workstream_count"] == 2
    assert list_payload["sessions"][0]["program_run_summary"]["id"] == "program-run-001"
    assert list_payload["sessions"][0]["program_run_summary"]["remaining_work_count"] == 1
    assert "state_before" not in list_payload["sessions"][0]

    detail_response = client.get(
        f"/api/v1/workspaces/{session.workspace_id}/meeting-sessions/{session.id}"
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == session.id
    assert "state_before" in detail_payload
    assert detail_payload["compile_job"]["session_id"] == session.id
    assert detail_payload["compile_job"]["metadata"]["route_kind"] == "meeting"
    assert "_internal_recovery_context" not in detail_payload["compile_job"]["metadata"]
    assert detail_payload["program_spec_summary"]["milestone_count"] == 1
    assert detail_payload["program_spec_summary"]["target_outputs"] == [
        "series_bible",
        "storyboard_seed_pack",
    ]
    assert detail_payload["program_run_summary"]["status"] == "open"
    assert detail_payload["program_run_summary"]["workstream_count"] == 2
    assert compile_job_calls == [session.id, session.id]


def test_meeting_session_events_endpoint_uses_high_enough_default_limit(monkeypatch):
    module = _load_meeting_sessions_module()
    session = _make_session()
    observed_calls = []

    class FakeMindEvent:
        def __init__(self, payload):
            self._payload = payload

        def model_dump(self, mode="json"):
            return self._payload

    class FakeMeetingSessionStore:
        def get_by_id(self, session_id):
            if session_id == session.id:
                return session
            return None

    class FakeMindscapeStore:
        def get_events_by_meeting_session(self, meeting_session_id, workspace_id=None, limit=500):
            observed_calls.append(
                {
                    "meeting_session_id": meeting_session_id,
                    "workspace_id": workspace_id,
                    "limit": limit,
                }
            )
            return [FakeMindEvent({"event_type": "meeting_end"})]

    monkeypatch.setattr(module, "MeetingSessionStore", lambda: FakeMeetingSessionStore())
    monkeypatch.setattr(module, "MindscapeStore", lambda: FakeMindscapeStore())

    app = FastAPI()
    app.include_router(module.router)
    client = ASGIAsyncTestClient(app)

    response = client.get(
        f"/api/v1/workspaces/{session.workspace_id}/meeting-sessions/{session.id}/events"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["events"][0]["event_type"] == "meeting_end"
    assert observed_calls == [
        {
            "meeting_session_id": session.id,
            "workspace_id": session.workspace_id,
            "limit": 2000,
        }
    ]


def test_project_card_endpoint_includes_compile_job_summary(monkeypatch):
    module = _load_project_stats_module()
    session = _make_session()
    job = _make_compile_job(session.id)
    compile_job_session_calls = []
    compile_job_project_calls = []
    fake_store = SimpleNamespace(
        db_path="/tmp/project-card-compile-job.sqlite",
        playbook_executions=SimpleNamespace(get_execution=lambda execution_id: None),
    )

    fake_tasks_store_module = types.ModuleType(
        "backend.app.services.stores.tasks_store"
    )

    class FakeTasksStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def list_executions_by_project(self, **kwargs):
            return []

        def list_executions_by_workspace(self, **kwargs):
            return []

    fake_tasks_store_module.TasksStore = FakeTasksStore

    fake_events_store_module = types.ModuleType(
        "backend.app.services.stores.events_store"
    )

    class FakeEventsStore:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_events_by_project(self, project_id, limit=200):
            return []

    fake_events_store_module.EventsStore = FakeEventsStore

    fake_artifact_registry_module = types.ModuleType(
        "backend.app.services.project.artifact_registry_service"
    )

    class FakeArtifactRegistryService:
        def __init__(self, store):
            self.store = store

        async def list_artifacts(self, project_id):
            return []

    fake_artifact_registry_module.ArtifactRegistryService = FakeArtifactRegistryService

    fake_playbook_registry_module = types.ModuleType(
        "backend.app.services.playbook_registry"
    )

    class FakePlaybookRegistry:
        async def get_playbook(self, playbook_code, locale="zh-TW"):
            return None

    fake_playbook_registry_module.PlaybookRegistry = FakePlaybookRegistry

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.stores.tasks_store",
        fake_tasks_store_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.stores.events_store",
        fake_events_store_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.project.artifact_registry_service",
        fake_artifact_registry_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.playbook_registry",
        fake_playbook_registry_module,
    )

    class FakeProjectManager:
        def __init__(self, store):
            self.store = store

        async def get_project(self, project_id, workspace_id=None):
            assert project_id == "proj-compile-001"
            assert workspace_id == "ws-compile-001"
            return SimpleNamespace(
                id=project_id,
                title="Compile Projection",
                type="campaign",
                flow_id="",
                state="open",
                metadata={"meeting_enabled": True},
                updated_at=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc),
            )

    class FakeMeetingSessionStore:
        def get_active_session(self, workspace_id, project_id=None, thread_id=None):
            assert workspace_id == session.workspace_id
            assert project_id == session.project_id
            return session

        def list_by_workspace(self, workspace_id, project_id=None, limit=5, offset=0):
            assert workspace_id == session.workspace_id
            assert project_id == session.project_id
            return [session]

    class FakeCompileJobStore:
        def get_latest_for_session(self, session_id):
            compile_job_session_calls.append(session_id)
            return job if session_id == session.id else None

        def get_latest_for_project(self, workspace_id, project_id):
            compile_job_project_calls.append((workspace_id, project_id))
            return None

    async def override_workspace():
        return SimpleNamespace(id=session.workspace_id)

    def override_store():
        return fake_store

    monkeypatch.setattr(module, "ProjectManager", FakeProjectManager)
    monkeypatch.setattr(module, "MeetingSessionStore", lambda: FakeMeetingSessionStore())
    monkeypatch.setattr(module, "CompileJobStore", lambda: FakeCompileJobStore())

    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[module.get_workspace] = override_workspace
    app.dependency_overrides[module.get_store] = override_store
    client = ASGIAsyncTestClient(app)

    response = client.get(
        f"/api/v1/workspaces/{session.workspace_id}/projects/{session.project_id}/card"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["projectId"] == session.project_id
    assert payload["meeting"]["session_id"] == session.id
    assert payload["meeting"]["status"] == "active"
    assert payload["meeting"]["compile_job"]["id"] == job.id
    assert payload["meeting"]["compile_job"]["status"] == "running"
    assert payload["meeting"]["compile_job"]["metadata"]["route_kind"] == "meeting"
    assert "_internal_recovery_context" not in payload["meeting"]["compile_job"]["metadata"]
    assert payload["meeting"]["program_spec_summary"]["source"] == "executor_structured"
    assert payload["meeting"]["program_spec_summary"]["workstream_count"] == 2
    assert payload["meeting"]["program_spec_summary"]["scale"] == "program"
    assert payload["meeting"]["program_run_summary"]["id"] == "program-run-001"
    assert payload["meeting"]["program_run_summary"]["remaining_work_count"] == 1
    assert payload["meeting"]["routing_prompt_mode_summary"]["health_status"] == "warning"
    assert payload["meeting"]["routing_prompt_mode_summary"]["compressed_ratio"] == 0.5
    assert compile_job_session_calls == [session.id]
    assert compile_job_project_calls == []

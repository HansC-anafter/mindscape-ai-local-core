import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import httpx
from fastapi import FastAPI

from backend.app.models.program_run import ProgramRun, ProgramRunStatus
from backend.app.models.workspace import Workspace


BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _load_program_runs_module():
    original_workspace_dependencies = sys.modules.get(
        "backend.app.routes.workspace_dependencies"
    )

    fake_workspace_dependencies_module = types.ModuleType(
        "backend.app.routes.workspace_dependencies"
    )

    async def fake_get_workspace():
        return None

    fake_workspace_dependencies_module.get_workspace = fake_get_workspace
    sys.modules["backend.app.routes.workspace_dependencies"] = (
        fake_workspace_dependencies_module
    )

    module_path = (
        BACKEND_ROOT
        / "app"
        / "routes"
        / "core"
        / "workspace"
        / "program_runs.py"
    )
    spec = importlib.util.spec_from_file_location(
        "workspace_program_runs_test_module",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        if original_workspace_dependencies is not None:
            sys.modules["backend.app.routes.workspace_dependencies"] = (
                original_workspace_dependencies
            )
        else:
            sys.modules.pop("backend.app.routes.workspace_dependencies", None)
    return module


module = _load_program_runs_module()


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


def _make_workspace() -> Workspace:
    return Workspace(
        id="ws-program-run-001",
        title="Program Run Workspace",
        owner_user_id="user-001",
        metadata={},
    )


def _make_program_run() -> ProgramRun:
    return ProgramRun.new(
        workspace_id="ws-program-run-001",
        meeting_session_id="session-program-run-001",
        project_id="proj-program-run-001",
        thread_id="thread-program-run-001",
        status=ProgramRunStatus.OPEN,
        source="executor_structured",
        scale="program",
        program_spec={
            "workstreams": [
                {
                    "id": "WS1",
                    "name": "Series Bible",
                    "description": "Draft the season bible.",
                    "eligible_engines": ["playbook:project_breakdown"],
                },
                {
                    "id": "WS2",
                    "name": "Storyboard Seeds",
                    "description": "Draft storyboard seeds.",
                    "eligible_engines": ["tool:storyboard.generate"],
                },
            ],
            "milestones": [
                {
                    "id": "M1",
                    "name": "Arc Gate",
                    "depends_on_streams": ["WS1"],
                    "deliverables": ["series_bible"],
                }
            ],
            "target_outputs": ["series_bible", "storyboard_seed_pack"],
            "scale": "program",
        },
        cursor_state={
            "remaining_work_count": 1,
            "completed_workstream_ids": ["WS1"],
            "remaining_workstream_ids": ["WS2"],
        },
        target_outputs=["series_bible", "storyboard_seed_pack"],
        metadata={"structured": True},
        program_run_id="program-run-001",
    )


def test_list_workspace_program_runs(monkeypatch):
    workspace = _make_workspace()
    program_run = _make_program_run()

    class FakeProgramRunStore:
        def list_by_workspace(
            self,
            workspace_id,
            *,
            project_id=None,
            meeting_session_id=None,
            limit=20,
            offset=0,
        ):
            assert workspace_id == workspace.id
            assert project_id == program_run.project_id
            assert meeting_session_id is None
            assert limit == 20
            assert offset == 0
            return [program_run]

        def get_by_id(self, program_run_id):
            if program_run_id == program_run.id:
                return program_run
            return None

    monkeypatch.setattr(module, "ProgramRunStore", lambda: FakeProgramRunStore())

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_workspace] = lambda: workspace
    client = ASGIAsyncTestClient(app)

    response = client.get(
        f"/{workspace.id}/program-runs",
        params={"project_id": program_run.project_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["program_runs"][0]["id"] == "program-run-001"
    assert payload["program_runs"][0]["source"] == "executor_structured"
    assert payload["program_runs"][0]["remaining_work_count"] == 1
    assert payload["program_runs"][0]["completed_work_count"] == 1


def test_get_workspace_program_run_detail(monkeypatch):
    workspace = _make_workspace()
    program_run = _make_program_run()

    class FakeProgramRunStore:
        def list_by_workspace(self, *args, **kwargs):
            return [program_run]

        def get_by_id(self, program_run_id):
            if program_run_id == program_run.id:
                return program_run
            return None

    monkeypatch.setattr(module, "ProgramRunStore", lambda: FakeProgramRunStore())

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_workspace] = lambda: workspace
    client = ASGIAsyncTestClient(app)

    response = client.get(f"/{workspace.id}/program-runs/{program_run.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "program-run-001"
    assert payload["program_spec"]["workstreams"][0]["id"] == "WS1"
    assert payload["cursor_state"]["remaining_workstream_ids"] == ["WS2"]
    assert payload["metadata"]["structured"] is True

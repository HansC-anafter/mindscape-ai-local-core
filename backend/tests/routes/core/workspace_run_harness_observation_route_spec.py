import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.models.run_harness import (
    RunHarnessEpisode,
    RunHarnessKind,
    RunHarnessObservation,
    RunHarnessResult,
    RunHarnessStatus,
)
from backend.app.models.workspace import Workspace

_ROUTE_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "routes"
    / "core"
    / "workspace"
    / "run_harness.py"
)
_ROUTE_SPEC = importlib.util.spec_from_file_location(
    "run_harness_route_under_test",
    _ROUTE_PATH,
)
assert _ROUTE_SPEC is not None and _ROUTE_SPEC.loader is not None
run_harness = importlib.util.module_from_spec(_ROUTE_SPEC)
_ROUTE_SPEC.loader.exec_module(run_harness)


class FakeEpisodeLedgerService:
    def __init__(self, observation):
        self.observation = observation

    def get_observation(self, episode_id):
        if episode_id == "missing":
            return None
        return self.observation


def _observation(workspace_id: str = "ws") -> RunHarnessObservation:
    return RunHarnessObservation(
        workspace_id=workspace_id,
        episode=RunHarnessEpisode(
            episode_id="episode-1",
            intent_envelope_ref="intent-1",
            selection_ref="selection-1",
            status=RunHarnessStatus.SUCCEEDED,
        ),
        result=RunHarnessResult(
            run_id="run-1",
            episode_id="episode-1",
            harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
            status=RunHarnessStatus.SUCCEEDED,
        ),
        source="unit",
    )


def _build_client(observation: RunHarnessObservation) -> TestClient:
    app = FastAPI()
    app.include_router(run_harness.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[run_harness.get_workspace] = lambda: Workspace(
        id="ws",
        title="Workspace",
        owner_user_id="user",
    )
    app.dependency_overrides[run_harness.get_store] = lambda: object()
    app.dependency_overrides[run_harness.get_episode_ledger_service] = (
        lambda: FakeEpisodeLedgerService(observation)
    )
    return TestClient(app)


def test_workspace_run_harness_episode_route_returns_single_observation() -> None:
    client = _build_client(_observation())

    response = client.get("/api/v1/workspaces/ws/run-harness/episodes/episode-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws"
    assert payload["episode"]["episode_id"] == "episode-1"
    assert payload["result"]["status"] == "succeeded"


def test_workspace_run_harness_episode_route_enforces_workspace_scope() -> None:
    client = _build_client(_observation(workspace_id="other-ws"))

    response = client.get("/api/v1/workspaces/ws/run-harness/episodes/episode-1")

    assert response.status_code == 404


def test_workspace_run_harness_route_does_not_expose_list_polling() -> None:
    client = _build_client(_observation())

    response = client.get("/api/v1/workspaces/ws/run-harness/episodes")

    assert response.status_code == 404

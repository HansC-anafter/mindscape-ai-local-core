from pathlib import Path

import pytest

from backend.app.dependencies.auth import AuthContext
from backend.app.services.meeting_product_admission import (
    admit_meeting_root,
    meeting_admission_context,
)


ROOT = Path(__file__).resolve().parents[4]


class FakeFacade:
    def __init__(self) -> None:
        self.requests = []

    async def admit_root(self, request):
        self.requests.append(request)
        snapshot = type(
            "Snapshot",
            (),
            {
                "schema_version": "mindscape.execution-admission-snapshot.v1",
                "snapshot_hash": "c" * 64,
                "model_dump": lambda self, *, mode: {
                    "workspace_id": request.workspace_id,
                    "root_execution_id": request.root_execution_id,
                    "snapshot_hash": "c" * 64,
                },
            },
        )()
        return type(
            "Admission",
            (),
            {"snapshot": snapshot, "external_decision": None},
        )()


@pytest.mark.asyncio
async def test_meeting_root_maps_scope_once_to_admission_facade():
    facade = FakeFacade()
    result = await admit_meeting_root(
        workspace_id="workspace-one",
        active_group_id="group-one",
        observed_topology_revision=9,
        product_surface_id="yogacoach.live_practice",
        selector_kind="api_prefix",
        selector_key="/api/v1/capabilities/yogacoach",
        operation_type="generate",
        execution_backend="local",
        remote_ingress_verified=True,
        auth=AuthContext(
            user_id="owner",
            tenant_id="local",
            workspace_ids=["workspace-one"],
            group_ids=["group-one"],
        ),
        trace_id="trace-one",
        root_execution_id="meeting-one",
        facade=facade,
    )

    assert result.snapshot is not None
    assert result.external_decision is None
    assert len(facade.requests) == 1
    request = facade.requests[0]
    assert request.entry == "remote"
    assert request.remote_ingress_verified is True
    assert request.product_surface_id == "yogacoach.live_practice"
    assert request.root_execution_id == "meeting-one"


def test_meeting_child_context_only_reuses_persisted_snapshot():
    session = type(
        "Session",
        (),
        {
            "metadata": {
                "execution_admission_snapshot": {"snapshot_hash": "a" * 64},
                "root_execution_id": "meeting-one",
            }
        },
    )()
    assert meeting_admission_context(session) == {
        "execution_admission_snapshot": {"snapshot_hash": "a" * 64},
        "root_execution_id": "meeting-one",
    }
    assert meeting_admission_context(None) == {}


def test_meeting_and_run_harness_admit_before_execution_or_store_write():
    meeting = (ROOT / "backend/app/routes/meeting_sessions.py").read_text(
        encoding="utf-8"
    )
    meeting_start_service = (
        ROOT / "backend/app/services/meeting_session_start.py"
    ).read_text(encoding="utf-8")
    run_harness = (
        ROOT / "backend/app/routes/core/workspace/run_harness.py"
    ).read_text(encoding="utf-8")
    meeting_start = meeting[meeting.index("async def start_session("):]
    assert "await start_meeting_session(" in meeting_start
    assert meeting_start_service.index(
        "await admit_meeting_root("
    ) < meeting_start_service.index(
        "store = MeetingSessionStore()"
    )
    assert run_harness.index("await admit_run_harness_root(") < (
        run_harness.index("return await service.execute(admitted.request)")
    )
    assert run_harness.rindex("await admit_run_harness_root(") < (
        run_harness.index("return await service.start(admitted.request)")
    )

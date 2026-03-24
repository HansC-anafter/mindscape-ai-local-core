from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.services.memory.writeback.legacy_metadata_memory_projection_adapter import (
    LegacyMetadataMemoryProjectionAdapter,
)


def _utc_now():
    return datetime.now(timezone.utc)


@dataclass
class _FakeService:
    calls: list = field(default_factory=list)

    async def add_projected_episode(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})


def test_legacy_metadata_projection_adapter_projects_to_all_metadata_surfaces():
    workspace_service = _FakeService()
    project_service = _FakeService()
    member_service = _FakeService()

    adapter = LegacyMetadataMemoryProjectionAdapter(
        workspace_core_memory_service=workspace_service,
        project_memory_service=project_service,
        member_profile_memory_service=member_service,
    )

    digest = SessionDigest(
        id="digest-1",
        source_type="meeting",
        source_id="sess-1",
        source_time_end=_utc_now(),
        owner_profile_id="profile-1",
        workspace_refs=["ws-1"],
        project_refs=["proj-1"],
        summary_md="We aligned on phase 1 and deferred merge lifecycle.",
        actions=[{"title": "Ship phase 1"}],
        decisions=[{"event_id": "dec-1"}],
    )

    adapter.dispatch_digest_projection(
        digest,
        source_memory_item_id="mem-1",
        source_writeback_run_id="run-1",
    )

    assert len(workspace_service.calls) == 1
    assert len(project_service.calls) == 1
    assert len(member_service.calls) == 1

    workspace_episode = workspace_service.calls[0]["args"][1]
    assert workspace_episode["canonical_projection"]["source_memory_item_id"] == "mem-1"
    assert workspace_episode["canonical_projection"]["source_writeback_run_id"] == "run-1"
    assert workspace_episode["title"] == "Meeting episode sess-1"

from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.services.knowledge_projection.group_context import (
    GroupKnowledgeAccessError,
    GroupKnowledgeContextReader,
)
import pytest
from backend.app.services.workspace_groups.contracts import (
    WorkspaceGroupMember,
    WorkspaceGroupTopologySnapshot,
)


class _Snapshots:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    def get(self, snapshot_id):
        self.calls += 1
        return self.snapshot if snapshot_id == self.snapshot.id else None


class _Groups:
    def __init__(self):
        self.calls = 0

    def get_group(self, group_id, **auth):
        self.calls += 1
        assert auth["actor_user_id"] == "user-1"
        return SimpleNamespace(id=group_id)


class _Memory:
    def __init__(self):
        self.calls = 0

    def list_for_context(self, **kwargs):
        self.calls += 1
        now = datetime(2026, 7, 15, tzinfo=timezone.utc)
        return [
            SimpleNamespace(
                id="mem-public",
                subject_type="topic",
                subject_id="public",
                title="Public",
                claim="Visible to every role",
                summary="",
                lifecycle_status="active",
                verification_status="verified",
                confidence=0.9,
                metadata={"stable_subject_key": "topic:public"},
                updated_at=now,
            ),
            SimpleNamespace(
                id="mem-teacher",
                subject_type="topic",
                subject_id="teacher",
                title="Teacher",
                claim="Teacher-only view",
                summary="",
                lifecycle_status="candidate",
                verification_status="observed",
                confidence=0.7,
                metadata={"allowed_agent_roles": ["teacher"]},
                updated_at=now,
            ),
        ]

    def context_revision(self, **kwargs):
        return "2:2026-07-15T00:00:00+00:00"


def test_group_packet_is_authorized_role_filtered_and_run_cached():
    snapshot = WorkspaceGroupTopologySnapshot(
        id="snapshot-1",
        group_id="group-1",
        display_name="Group",
        group_revision=3,
        content_hash="a" * 64,
        members=[WorkspaceGroupMember(workspace_id="workspace-1", role="dispatch")],
        dispatch_workspace_id="workspace-1",
        created_by_user_id="user-1",
    )
    snapshots = _Snapshots(snapshot)
    groups = _Groups()
    memory = _Memory()
    reader = GroupKnowledgeContextReader(
        snapshot_service=snapshots,
        group_facade=groups,
        memory_store=memory,
    )

    first = reader.compile_packet(
        topology_snapshot_id="snapshot-1",
        requesting_workspace_id="workspace-1",
        actor_user_id="user-1",
        agent_role="student",
        preview=True,
    )
    second = reader.compile_packet(
        topology_snapshot_id="snapshot-1",
        requesting_workspace_id="workspace-1",
        actor_user_id="user-1",
        agent_role="student",
        preview=True,
    )

    assert first is second
    assert [entry.memory_item_id for entry in first.entries] == ["mem-public"]
    assert first.bound_agent_role == "dispatch"
    assert first.preview is True
    assert snapshots.calls == groups.calls == 2
    assert memory.calls == 1


def test_group_packet_rejects_caller_selected_run_role():
    snapshot = WorkspaceGroupTopologySnapshot(
        id="snapshot-1",
        group_id="group-1",
        display_name="Group",
        group_revision=3,
        content_hash="a" * 64,
        members=[
            WorkspaceGroupMember(
                workspace_id="workspace-1",
                role="dispatch",
            )
        ],
        dispatch_workspace_id="workspace-1",
        created_by_user_id="user-1",
    )
    reader = GroupKnowledgeContextReader(
        snapshot_service=_Snapshots(snapshot),
        group_facade=_Groups(),
        memory_store=_Memory(),
    )

    with pytest.raises(
        GroupKnowledgeAccessError,
        match="differs from the admitted topology",
    ):
        reader.compile_packet(
            topology_snapshot_id="snapshot-1",
            requesting_workspace_id="workspace-1",
            actor_user_id="user-1",
            agent_role="teacher",
            preview=False,
        )

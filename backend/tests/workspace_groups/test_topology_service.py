from contextlib import contextmanager
import pytest
from pydantic import ValidationError

from backend.app.services.workspace_groups.context_resolver import (
    WorkspaceGroupContextResolver,
)
from backend.app.services.workspace_groups.contracts import (
    WorkspaceGroupCreate,
    WorkspaceGroupMemberInput,
    WorkspaceGroupTopology,
    WorkspaceGroupUpdate,
)
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupAccessError,
    WorkspaceGroupTopologyService,
)


def _topology(owner="owner", members=None, revision=1):
    return WorkspaceGroupTopology(
        id="group-1",
        display_name="Group 1",
        owner_user_id=owner,
        revision=revision,
        members=members or [],
    )


class FakeRepository:
    def __init__(self, topology=None):
        self.topology = topology
        self.calls = []

    @contextmanager
    def transaction(self):
        self.calls.append("transaction")
        yield object()

    @staticmethod
    def serialize_json(value):
        return "{}"

    def verify_workspaces(self, conn, workspace_ids):
        self.calls.append(("verify", list(workspace_ids)))
        return {workspace_id: "owner" for workspace_id in workspace_ids}

    def create_definition(self, conn, **values):
        self.calls.append(("create_definition", values["group_id"]))
        self.topology = WorkspaceGroupTopology(
            id=values["group_id"],
            display_name=values["display_name"],
            owner_user_id=values["owner_user_id"],
            description=values["description"],
        )

    def replace_members(self, conn, *, group_id, members):
        member_rows = list(members)
        self.calls.append(("replace_members", member_rows))
        payload = self.topology.model_dump()
        payload["members"] = member_rows
        payload["revision"] += 1
        self.topology = WorkspaceGroupTopology.model_validate(payload)

    def get(self, group_id):
        return self.topology if self.topology and self.topology.id == group_id else None

    def update_definition(self, conn, *, group_id, values):
        self.calls.append(("update_definition", values))

    def delete_definition(self, conn, group_id):
        self.calls.append(("delete_definition", group_id))
        return True

    def list_for_workspace(self, workspace_id):
        return [self.topology] if self.topology else []


def test_create_uses_one_transaction_and_normalized_members():
    repository = FakeRepository()
    service = WorkspaceGroupTopologyService(repository)
    result = service.create(
        WorkspaceGroupCreate(
            id="group-1",
            display_name="Group 1",
            members=[
                WorkspaceGroupMemberInput(workspace_id="dispatch", role="dispatch"),
                WorkspaceGroupMemberInput(workspace_id="cell", role="cell"),
            ],
        ),
        actor_user_id="owner",
        allowed_workspace_ids=["dispatch", "cell"],
    )

    assert result.is_ready is True
    assert repository.calls[0] == "transaction"
    assert [call[0] for call in repository.calls[1:]] == [
        "verify",
        "create_definition",
        "replace_members",
    ]


def test_non_owner_cannot_mutate_even_when_group_read_is_allowed():
    service = WorkspaceGroupTopologyService(FakeRepository(_topology()))
    with pytest.raises(WorkspaceGroupAccessError, match="only the group owner"):
        service.update(
            "group-1",
            WorkspaceGroupUpdate(display_name="Changed"),
            actor_user_id="member",
            allowed_group_ids=["group-1"],
        )


def test_context_requires_explicit_group_and_workspace_membership():
    topology = _topology(
        members=[{"workspace_id": "dispatch", "role": "dispatch"}],
        revision=4,
    )
    service = WorkspaceGroupTopologyService(FakeRepository(topology))
    resolver = WorkspaceGroupContextResolver(service)

    assert resolver.resolve(
        active_group_id=None,
        workspace_id="dispatch",
        actor_user_id="owner",
    ) is None
    context = resolver.resolve(
        active_group_id="group-1",
        workspace_id="dispatch",
        actor_user_id="owner",
    )
    assert context and context.revision == 4 and context.role == "dispatch"

    with pytest.raises(WorkspaceGroupAccessError, match="not in active group"):
        resolver.resolve(
            active_group_id="group-1",
            workspace_id="outside",
            actor_user_id="owner",
        )


@pytest.mark.parametrize(
    "members",
    [
        [
            {"workspace_id": "same", "role": "dispatch"},
            {"workspace_id": "same", "role": "cell"},
        ],
        [
            {"workspace_id": "one", "role": "dispatch"},
            {"workspace_id": "two", "role": "dispatch"},
        ],
    ],
)
def test_invalid_member_sets_fail_before_database_access(members):
    with pytest.raises(ValidationError):
        WorkspaceGroupCreate(display_name="Invalid", members=members)

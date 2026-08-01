import json
from contextlib import contextmanager

from backend.app.models.object_runtime import (
    ObjectInstanceRecord,
    ObjectRef,
    ObjectRelationRecord,
)
from backend.app.services.stores.object_instance_registry_store import (
    ObjectInstanceRegistryStore,
)
from backend.app.services.stores.object_relation_registry_store import (
    ObjectRelationRegistryStore,
)


class _Connection:
    def __init__(self, state, calls):
        self.state = state
        self.calls = calls

    def execute(self, statement, params):
        assert self.state["open"] is True
        self.calls.append((str(statement), params))


def _attach_transaction(store):
    state = {"open": False, "entered": 0}
    calls = []

    @contextmanager
    def _transaction():
        state["open"] = True
        state["entered"] += 1
        try:
            yield _Connection(state, calls)
        finally:
            state["open"] = False

    store.transaction = _transaction
    return state, calls


def _ref(object_id: str) -> ObjectRef:
    return ObjectRef(
        uri=f"mindscape://pack/kind/{object_id}",
        owner_pack="pack",
        object_kind="kind",
        object_id=object_id,
        workspace_id="workspace-a",
        selector={"id": object_id},
        source_surface="workbench",
    )


def test_empty_registry_batches_do_not_acquire_transactions():
    instance_store = object.__new__(ObjectInstanceRegistryStore)
    relation_store = object.__new__(ObjectRelationRegistryStore)

    def _unexpected_transaction():
        raise AssertionError("empty batches must not acquire a transaction")

    instance_store.transaction = _unexpected_transaction
    relation_store.transaction = _unexpected_transaction

    assert instance_store.upsert_many("workspace-a", []) == 0
    assert relation_store.upsert_many("workspace-a", []) == 0


def test_instance_batch_prepares_before_one_ordered_execute():
    store = object.__new__(ObjectInstanceRegistryStore)
    state, calls = _attach_transaction(store)
    serialize_json = store.serialize_json
    search_ids = []

    def _serialize(value):
        assert state["open"] is False
        return serialize_json(value)

    def _build_search_text(record):
        assert state["open"] is False
        search_ids.append(record.ref.object_id)
        return f"search-{record.ref.object_id}"

    store.serialize_json = _serialize
    store._build_search_text = _build_search_text
    records = [
        ObjectInstanceRecord(
            ref=_ref("object-1"),
            title="Object 1",
            labels=["one"],
            mention_tokens=["@one"],
            affordance_verbs=["open"],
            metadata={"rank": 1},
            updated_at="2026-08-01T19:00:00Z",
        ),
        ObjectInstanceRecord(
            ref=_ref("object-2"),
            title="Object 2",
            labels=["two"],
            mention_tokens=["@two"],
            affordance_verbs=["inspect"],
            metadata={"rank": 2},
            updated_at="2026-08-01T19:01:00Z",
        ),
    ]

    assert store.upsert_many("workspace-a", records) == 2

    assert state == {"open": False, "entered": 1}
    assert search_ids == ["object-1", "object-2"]
    assert len(calls) == 1
    statement, bound_params = calls[0]
    assert "INSERT INTO object_instances" in statement
    assert "jsonb_to_recordset" in statement
    assert "DISTINCT ON (workspace_id, uri)" in statement
    assert "ON CONFLICT (workspace_id, uri) DO UPDATE" in statement
    assert set(bound_params) == {"records"}
    payload = json.loads(bound_params["records"])
    assert [item["ordinal"] for item in payload] == [0, 1]
    assert [item["object_id"] for item in payload] == ["object-1", "object-2"]
    assert [item["search_text"] for item in payload] == [
        "search-object-1",
        "search-object-2",
    ]
    assert payload[0]["selector"] == {"id": "object-1"}
    assert payload[0]["labels"] == ["one"]
    assert payload[0]["mention_tokens"] == ["@one"]
    assert payload[0]["affordance_verbs"] == ["open"]
    assert payload[0]["metadata"] == {"rank": 1}
    assert set(payload[0]) == {
        "ordinal",
        "workspace_id",
        "uri",
        "owner_pack",
        "object_kind",
        "object_id",
        "version",
        "selector",
        "source_surface",
        "title",
        "subtitle",
        "summary_text",
        "labels",
        "thumbnail_ref",
        "owner_surface_url",
        "mention_tokens",
        "mention_text",
        "search_text",
        "affordance_verbs",
        "stale",
        "metadata",
        "updated_at",
    }


def test_relation_batch_prepares_before_one_ordered_execute():
    store = object.__new__(ObjectRelationRegistryStore)
    state, calls = _attach_transaction(store)
    serialize_json = store.serialize_json
    derived_ids = []

    def _serialize(value):
        assert state["open"] is False
        return serialize_json(value)

    def _build_relation_id(*, workspace_id, relation):
        assert state["open"] is False
        assert workspace_id == "workspace-a"
        derived_ids.append(relation.target_ref.object_id)
        return f"derived-{relation.target_ref.object_id}"

    store.serialize_json = _serialize
    store._build_relation_id = _build_relation_id
    relations = [
        ObjectRelationRecord(
            relation_id="explicit-relation",
            source_ref=_ref("source-1"),
            relation_kind="supports",
            target_ref=_ref("target-1"),
            source_role="source",
            target_role="target",
            provenance_type="test",
            provenance_id="proof-1",
            meeting_id="meeting-1",
            metadata={"rank": 1},
            created_at="2026-08-01T19:00:00Z",
            updated_at="2026-08-01T19:01:00Z",
        ),
        ObjectRelationRecord(
            source_ref=_ref("source-2"),
            relation_kind="supports",
            target_ref=_ref("target-2"),
            metadata={"rank": 2},
        ),
    ]

    assert store.upsert_many("workspace-a", relations) == 2

    assert state == {"open": False, "entered": 1}
    assert derived_ids == ["target-2"]
    assert len(calls) == 1
    statement, bound_params = calls[0]
    assert "INSERT INTO object_relations" in statement
    assert "jsonb_to_recordset" in statement
    assert "first_value(created_at)" in statement
    assert "WHERE latest_rank = 1" in statement
    assert "ON CONFLICT (workspace_id, relation_id) DO UPDATE" in statement
    assert set(bound_params) == {"relations"}
    payload = json.loads(bound_params["relations"])
    assert [item["ordinal"] for item in payload] == [0, 1]
    assert [item["relation_id"] for item in payload] == [
        "explicit-relation",
        "derived-target-2",
    ]
    assert [item["target_uri"] for item in payload] == [
        "mindscape://pack/kind/target-1",
        "mindscape://pack/kind/target-2",
    ]
    assert payload[0]["source_ref"]["object_id"] == "source-1"
    assert payload[0]["target_ref"]["object_id"] == "target-1"
    assert payload[0]["metadata"] == {"rank": 1}
    assert set(payload[0]) == {
        "ordinal",
        "workspace_id",
        "relation_id",
        "source_uri",
        "relation_kind",
        "target_uri",
        "source_ref",
        "target_ref",
        "source_role",
        "target_role",
        "provenance_type",
        "provenance_id",
        "meeting_id",
        "metadata",
        "created_at",
        "updated_at",
    }

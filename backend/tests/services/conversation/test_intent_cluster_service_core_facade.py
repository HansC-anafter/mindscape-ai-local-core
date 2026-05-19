from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from backend.app.models.mindscape import IntentCard, IntentCluster, IntentStatus
from backend.app.services.conversation import intent_cluster_service as facade_module
from backend.app.services.conversation.intent_cluster_service import IntentClusterService
from backend.app.services.conversation.intent_cluster_service_core import (
    clustering,
    labels,
    persistence,
    runtime,
)


class FakeEmbeddingGenerator:
    def __init__(self, store):
        self.store = store

    async def generate_embeddings_batch(self, intent_cards):
        return {intent.id: [float(index), 1.0] for index, intent in enumerate(intent_cards)}


class FakeClustersStore:
    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.created = []
        self.updated = []

    def list_clusters(self, **kwargs):
        return list(self.existing)

    def create_cluster(self, cluster):
        self.created.append(cluster)
        return cluster

    def update_cluster(self, cluster):
        self.updated.append(cluster)
        return cluster


class FakeIntentSink:
    def __init__(self):
        self.updated = []

    def update_intent(self, intent):
        self.updated.append(intent)
        return intent


class FakeStore:
    def __init__(self, intents):
        self._intents = {intent.id: intent for intent in intents}
        self.intents = FakeIntentSink()

    def list_intents(self, **kwargs):
        return list(self._intents.values())

    def get_intent(self, intent_id):
        return self._intents.get(intent_id)


def make_intent(intent_id, title, status=IntentStatus.ACTIVE):
    return IntentCard(
        id=intent_id,
        profile_id="profile_1",
        title=title,
        description=f"{title} description",
        status=status,
    )


def make_cluster(cluster_id, intent_ids, label="Existing"):
    now = datetime.now(timezone.utc)
    return IntentCluster(
        id=cluster_id,
        label=label,
        embedding=[1.0, 0.0],
        workspace_id="ws_1",
        profile_id="profile_1",
        intent_card_ids=list(intent_ids),
        metadata={},
        created_at=now,
        updated_at=now,
    )


def test_intent_cluster_service_method_surface_and_constructor(monkeypatch):
    expected = [
        "generate_embeddings",
        "cluster_intents",
        "_perform_kmeans_clustering",
        "_simple_distance_clustering",
        "generate_cluster_label",
        "update_intent_card_clusters",
        "_find_existing_cluster",
    ]

    monkeypatch.setattr(facade_module, "IntentClustersStore", FakeClustersStore)
    monkeypatch.setattr(facade_module, "IntentEmbeddingGenerator", FakeEmbeddingGenerator)

    store = FakeStore([])
    service = IntentClusterService(store)

    assert [name for name in expected if not hasattr(IntentClusterService, name)] == []
    assert service.store is store
    assert isinstance(service.clusters_store, FakeClustersStore)
    assert isinstance(service.embedding_generator, FakeEmbeddingGenerator)
    assert service.embedding_generator.store is store


@pytest.mark.asyncio
async def test_intent_cluster_service_facade_delegates(monkeypatch):
    service = IntentClusterService.__new__(IntentClusterService)
    service.store = object()
    service.clusters_store = object()
    service.embedding_generator = SimpleNamespace(
        generate_embeddings_batch=AsyncMock(return_value={"intent_1": [1.0]})
    )
    observed = {}

    async def fake_cluster_intents(**kwargs):
        observed["cluster"] = kwargs
        return ["cluster"]

    async def fake_perform_kmeans(**kwargs):
        observed["kmeans"] = kwargs
        return [["intent_1"]]

    async def fake_generate_label(**kwargs):
        observed["label"] = kwargs
        return "Label"

    async def fake_update_clusters(**kwargs):
        observed["update"] = kwargs

    monkeypatch.setattr(facade_module, "cluster_intents_helper", fake_cluster_intents)
    monkeypatch.setattr(facade_module, "perform_kmeans_clustering", fake_perform_kmeans)
    monkeypatch.setattr(facade_module, "generate_cluster_label_helper", fake_generate_label)
    monkeypatch.setattr(
        facade_module,
        "update_intent_card_clusters_helper",
        fake_update_clusters,
    )
    monkeypatch.setattr(
        facade_module,
        "simple_distance_clustering",
        lambda **kwargs: [["simple"]],
    )
    monkeypatch.setattr(
        facade_module,
        "find_existing_cluster",
        lambda **kwargs: "existing",
    )

    assert await service.generate_embeddings([make_intent("intent_1", "A")]) == {
        "intent_1": [1.0]
    }
    assert await service.cluster_intents("ws_1", "profile_1", n_clusters=2) == [
        "cluster"
    ]
    assert await service._perform_kmeans_clustering(
        np.array([[1.0]]),
        ["intent_1"],
        1,
    ) == [["intent_1"]]
    assert service._simple_distance_clustering(
        np.array([[1.0]]),
        ["intent_1"],
        1,
    ) == [["simple"]]
    assert await service.generate_cluster_label([make_intent("intent_1", "A")]) == "Label"
    await service.update_intent_card_clusters([])
    assert service._find_existing_cluster(make_cluster("c1", ["intent_1"]), "ws_1", "profile_1") == "existing"
    assert observed["cluster"]["service"] is service
    assert observed["kmeans"]["intent_ids"] == ["intent_1"]
    assert observed["label"]["cluster_intent_cards"][0].id == "intent_1"
    assert observed["update"]["store"] is service.store


def test_simple_distance_clustering_assigns_nearest_center():
    clusters = clustering.simple_distance_clustering(
        embeddings_matrix=np.array(
            [
                [1.0, 0.0],
                [0.0, 1.0],
                [0.9, 0.1],
                [0.1, 0.9],
            ]
        ),
        intent_ids=["a", "b", "c", "d"],
        n_clusters=2,
    )

    assert clusters == [["a", "c"], ["b", "d"]]
    assert clustering.simple_distance_clustering(
        np.array([[1.0], [2.0]]),
        ["a", "b"],
        3,
    ) == [["a"], ["b"]]


@pytest.mark.asyncio
async def test_kmeans_falls_back_when_loader_fails(monkeypatch):
    def raise_import_error():
        raise ImportError("missing sklearn")

    monkeypatch.setattr(clustering, "load_kmeans", raise_import_error)

    assert await clustering.perform_kmeans_clustering(
        embeddings_matrix=np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.2]]),
        intent_ids=["a", "b", "c"],
        n_clusters=2,
    ) == [["a", "c"], ["b"]]


@pytest.mark.asyncio
async def test_runtime_cluster_intents_creates_clusters_and_updates_metadata():
    active_intents = [
        make_intent("a", "Launch campaign"),
        make_intent("b", "Draft content"),
        make_intent("c", "Archive", status=IntentStatus.ARCHIVED),
    ]
    store = FakeStore(active_intents)
    clusters_store = FakeClustersStore()

    service = SimpleNamespace(
        store=store,
        clusters_store=clusters_store,
        generate_embeddings=AsyncMock(
            return_value={"a": [1.0, 0.0], "b": [0.0, 1.0]}
        ),
        _perform_kmeans_clustering=AsyncMock(return_value=[["a"], ["b"]]),
        generate_cluster_label=AsyncMock(side_effect=["Alpha", "Beta"]),
        update_intent_card_clusters=None,
        _find_existing_cluster=lambda cluster, workspace_id, profile_id: None,
    )
    service.update_intent_card_clusters = lambda clusters: persistence.update_intent_card_clusters(
        store=store,
        clusters=clusters,
    )

    result = await runtime.cluster_intents(
        service=service,
        workspace_id="ws_1",
        profile_id="profile_1",
        n_clusters=2,
    )

    assert [cluster.label for cluster in result] == ["Alpha", "Beta"]
    assert [cluster.intent_card_ids for cluster in result] == [["a"], ["b"]]
    assert len(clusters_store.created) == 2
    assert store._intents["a"].metadata["cluster_label"] == "Alpha"
    assert store._intents["b"].metadata["cluster_label"] == "Beta"
    assert len(store.intents.updated) == 2
    service.generate_embeddings.assert_awaited_once()
    service._perform_kmeans_clustering.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_cluster_intents_returns_empty_for_small_or_missing_inputs():
    one_intent_service = SimpleNamespace(
        store=FakeStore([make_intent("a", "A")]),
        clusters_store=FakeClustersStore(),
    )
    assert await runtime.cluster_intents(
        service=one_intent_service,
        workspace_id="ws_1",
        profile_id="profile_1",
    ) == []

    missing_embeddings_service = SimpleNamespace(
        store=FakeStore([make_intent("a", "A"), make_intent("b", "B")]),
        clusters_store=FakeClustersStore(),
        generate_embeddings=AsyncMock(return_value={}),
    )
    assert await runtime.cluster_intents(
        service=missing_embeddings_service,
        workspace_id="ws_1",
        profile_id="profile_1",
    ) == []


def test_persistence_find_existing_cluster_ignores_intent_order():
    existing = make_cluster("existing", ["b", "a"])
    clusters_store = FakeClustersStore(existing=[existing])

    assert (
        persistence.find_existing_cluster(
            clusters_store=clusters_store,
            new_cluster=make_cluster("new", ["a", "b"]),
            workspace_id="ws_1",
            profile_id="profile_1",
        )
        is existing
    )


def test_persist_intent_clusters_updates_existing_or_creates_new():
    existing = make_cluster("existing", ["a"])
    replacement = make_cluster("replacement", ["a"], label="Replacement")
    new_cluster = make_cluster("new", ["b"], label="New")
    clusters_store = FakeClustersStore(existing=[existing])

    persistence.persist_intent_clusters(
        clusters_store=clusters_store,
        intent_clusters=[replacement, new_cluster],
        workspace_id="ws_1",
        profile_id="profile_1",
        find_existing_cluster_fn=lambda cluster, workspace_id, profile_id: (
            existing if cluster.intent_card_ids == ["a"] else None
        ),
    )

    assert existing.label == "Replacement"
    assert clusters_store.updated == [existing]
    assert clusters_store.created == [new_cluster]


@pytest.mark.asyncio
async def test_generate_cluster_label_fallbacks_and_success(monkeypatch):
    intent = make_intent("a", "Launch campaign roadmap")

    assert await labels.generate_cluster_label([]) == "Unnamed Cluster"

    monkeypatch.setattr(
        labels,
        "load_llm_helpers",
        lambda: (
            AsyncMock(),
            lambda **kwargs: [{"role": "user", "content": kwargs["user_prompt"]}],
            object,
            lambda: None,
        ),
    )
    assert await labels.generate_cluster_label([intent]) == "Launch campaign roadmap"

    async def fake_call_llm(**kwargs):
        return {"text": "\"Launch Plan\""}

    monkeypatch.setattr(
        labels,
        "load_llm_helpers",
        lambda: (
            fake_call_llm,
            lambda **kwargs: [{"role": "user", "content": kwargs["user_prompt"]}],
            object,
            lambda: "model-a",
        ),
    )
    assert await labels.generate_cluster_label([intent]) == "Launch Plan"

    async def failing_call_llm(**kwargs):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(
        labels,
        "load_llm_helpers",
        lambda: (
            failing_call_llm,
            lambda **kwargs: [{"role": "user", "content": kwargs["user_prompt"]}],
            object,
            lambda: "model-a",
        ),
    )
    assert await labels.generate_cluster_label([intent]) == "Launch campaign roadmap"

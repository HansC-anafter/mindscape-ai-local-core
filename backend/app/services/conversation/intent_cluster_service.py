"""Intent cluster service facade."""

from typing import Dict, List, Optional

import numpy as np

from backend.app.models.mindscape import IntentCard, IntentCluster
from backend.app.services.conversation.intent_cluster_service_core import (
    cluster_intents as cluster_intents_helper,
    find_existing_cluster,
    generate_cluster_label as generate_cluster_label_helper,
    perform_kmeans_clustering,
    simple_distance_clustering,
    update_intent_card_clusters as update_intent_card_clusters_helper,
    utc_now as _utc_now,
)
from backend.app.services.conversation.intent_embedding_generator import (
    IntentEmbeddingGenerator,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.intent_clusters_store import IntentClustersStore


class IntentClusterService:
    """Clusters IntentCards by semantic similarity using embeddings."""

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.clusters_store = IntentClustersStore()
        self.embedding_generator = IntentEmbeddingGenerator(store=store)

    async def generate_embeddings(
        self,
        intent_cards: List[IntentCard],
    ) -> Dict[str, List[float]]:
        """Generate embeddings for IntentCards."""
        return await self.embedding_generator.generate_embeddings_batch(intent_cards)

    async def cluster_intents(
        self,
        workspace_id: str,
        profile_id: str,
        n_clusters: Optional[int] = None,
    ) -> List[IntentCluster]:
        """Cluster IntentCards for a workspace/profile."""
        return await cluster_intents_helper(
            service=self,
            workspace_id=workspace_id,
            profile_id=profile_id,
            n_clusters=n_clusters,
        )

    async def _perform_kmeans_clustering(
        self,
        embeddings_matrix: np.ndarray,
        intent_ids: List[str],
        n_clusters: int,
    ) -> List[List[str]]:
        return await perform_kmeans_clustering(
            embeddings_matrix=embeddings_matrix,
            intent_ids=intent_ids,
            n_clusters=n_clusters,
        )

    def _simple_distance_clustering(
        self,
        embeddings_matrix: np.ndarray,
        intent_ids: List[str],
        n_clusters: int,
    ) -> List[List[str]]:
        return simple_distance_clustering(
            embeddings_matrix=embeddings_matrix,
            intent_ids=intent_ids,
            n_clusters=n_clusters,
        )

    async def generate_cluster_label(
        self,
        cluster_intent_cards: List[IntentCard],
    ) -> str:
        """Generate a cluster label."""
        return await generate_cluster_label_helper(
            cluster_intent_cards=cluster_intent_cards,
        )

    async def update_intent_card_clusters(
        self,
        clusters: List[IntentCluster],
    ):
        return await update_intent_card_clusters_helper(
            store=self.store,
            clusters=clusters,
        )

    def _find_existing_cluster(
        self,
        new_cluster: IntentCluster,
        workspace_id: str,
        profile_id: str,
    ) -> Optional[IntentCluster]:
        return find_existing_cluster(
            clusters_store=self.clusters_store,
            new_cluster=new_cluster,
            workspace_id=workspace_id,
            profile_id=profile_id,
        )

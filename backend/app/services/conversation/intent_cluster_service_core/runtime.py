"""Runtime orchestration for intent clustering."""

import logging
from typing import List, Optional

import numpy as np

from backend.app.models.mindscape import IntentCluster
from backend.app.services.conversation.intent_cluster_service_core.persistence import (
    build_intent_cluster,
    persist_intent_clusters,
)

logger = logging.getLogger(__name__)


async def cluster_intents(
    *,
    service,
    workspace_id: str,
    profile_id: str,
    n_clusters: Optional[int] = None,
) -> List[IntentCluster]:
    """Cluster IntentCards for a workspace/profile."""
    try:
        logger.info(
            "IntentClusterService: Starting clustering for workspace=%s, profile=%s",
            workspace_id,
            profile_id,
        )

        intent_cards = service.store.list_intents(profile_id=profile_id)
        active_intents = [
            intent for intent in intent_cards if intent.status.value == "active"
        ]

        if len(active_intents) < 2:
            logger.info("Not enough IntentCards for clustering (need at least 2)")
            return []

        logger.info("Generating embeddings for %s IntentCards...", len(active_intents))

        existing_clusters = service.clusters_store.list_clusters(
            workspace_id=workspace_id,
            profile_id=profile_id,
        )

        intents_with_cluster = set()
        for cluster in existing_clusters:
            intents_with_cluster.update(cluster.intent_card_ids)

        intents_to_embed = [
            intent for intent in active_intents if intent.id not in intents_with_cluster
        ]

        if intents_to_embed:
            embeddings_dict = await service.generate_embeddings(intents_to_embed)
        else:
            embeddings_dict = {}

        if len(embeddings_dict) < 2 and len(active_intents) >= 2:
            embeddings_dict = await service.generate_embeddings(active_intents)

        if len(embeddings_dict) < 2:
            logger.warning("Not enough embeddings generated for clustering")
            return []

        intent_ids = list(embeddings_dict.keys())
        embeddings_matrix = np.array(
            [embeddings_dict[intent_id] for intent_id in intent_ids]
        )

        if n_clusters is None:
            n_clusters = max(2, min(10, int(np.sqrt(len(intent_ids)))))

        n_clusters = min(n_clusters, len(intent_ids))

        clusters = await service._perform_kmeans_clustering(
            embeddings_matrix=embeddings_matrix,
            intent_ids=intent_ids,
            n_clusters=n_clusters,
        )

        intent_clusters = []
        for cluster_idx, cluster_intent_ids in enumerate(clusters):
            if not cluster_intent_ids:
                continue

            cluster_intent_cards = [
                intent for intent in active_intents if intent.id in cluster_intent_ids
            ]
            cluster_label = await service.generate_cluster_label(
                cluster_intent_cards=cluster_intent_cards,
            )
            cluster_embeddings = [
                embeddings_dict[intent_id] for intent_id in cluster_intent_ids
            ]
            cluster_center = np.mean(cluster_embeddings, axis=0).tolist()
            intent_clusters.append(
                build_intent_cluster(
                    label=cluster_label,
                    embedding=cluster_center,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    intent_card_ids=cluster_intent_ids,
                    cluster_index=cluster_idx,
                )
            )

        persist_intent_clusters(
            clusters_store=service.clusters_store,
            intent_clusters=intent_clusters,
            workspace_id=workspace_id,
            profile_id=profile_id,
            find_existing_cluster_fn=service._find_existing_cluster,
        )
        await service.update_intent_card_clusters(intent_clusters)

        logger.info(
            "IntentClusterService: Created %s clusters for %s IntentCards",
            len(intent_clusters),
            len(active_intents),
        )

        return intent_clusters

    except Exception as exc:
        logger.error("Failed to cluster intents: %s", exc, exc_info=True)
        return []

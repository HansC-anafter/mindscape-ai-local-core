"""Persistence helpers for intent clusters."""

import logging
import uuid
from typing import List, Optional

from backend.app.models.mindscape import IntentCard, IntentCluster
from backend.app.services.conversation.intent_cluster_service_core.clock import utc_now

logger = logging.getLogger(__name__)


def build_intent_cluster(
    *,
    label: str,
    embedding: List[float],
    workspace_id: str,
    profile_id: str,
    intent_card_ids: List[str],
    cluster_index: int,
) -> IntentCluster:
    """Build an IntentCluster model from clustered intent ids."""
    return IntentCluster(
        id=str(uuid.uuid4()),
        label=label,
        embedding=embedding,
        workspace_id=workspace_id,
        profile_id=profile_id,
        intent_card_ids=intent_card_ids,
        metadata={
            "cluster_index": cluster_index,
            "intent_count": len(intent_card_ids),
            "created_at": utc_now().isoformat(),
        },
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def persist_intent_clusters(
    *,
    clusters_store,
    intent_clusters: List[IntentCluster],
    workspace_id: str,
    profile_id: str,
    find_existing_cluster_fn,
):
    """Create or update intent clusters in the configured cluster store."""
    for cluster in intent_clusters:
        existing = find_existing_cluster_fn(cluster, workspace_id, profile_id)
        if existing:
            existing.label = cluster.label
            existing.embedding = cluster.embedding
            existing.intent_card_ids = cluster.intent_card_ids
            existing.metadata = cluster.metadata
            existing.updated_at = utc_now()
            clusters_store.update_cluster(existing)
        else:
            clusters_store.create_cluster(cluster)


async def update_intent_card_clusters(*, store, clusters: List[IntentCluster]):
    """Update IntentCard metadata with cluster information."""
    try:
        for cluster in clusters:
            for intent_id in cluster.intent_card_ids:
                intent = store.get_intent(intent_id)
                if intent:
                    if not intent.metadata:
                        intent.metadata = {}
                    intent.metadata.update(
                        {
                            "cluster_id": cluster.id,
                            "cluster_label": cluster.label,
                        }
                    )
                    intent.updated_at = utc_now()
                    store.intents.update_intent(intent)

        logger.info(
            "Updated %s IntentCards with cluster information",
            sum(len(cluster.intent_card_ids) for cluster in clusters),
        )

    except Exception as exc:
        logger.error("Failed to update IntentCard clusters: %s", exc, exc_info=True)


def find_existing_cluster(
    *,
    clusters_store,
    new_cluster: IntentCluster,
    workspace_id: str,
    profile_id: str,
) -> Optional[IntentCluster]:
    """Find an existing cluster with the same intent card ids."""
    existing_clusters = clusters_store.list_clusters(
        workspace_id=workspace_id,
        profile_id=profile_id,
    )

    new_ids_set = set(new_cluster.intent_card_ids)
    for existing in existing_clusters:
        existing_ids_set = set(existing.intent_card_ids)
        if new_ids_set == existing_ids_set:
            return existing

    return None

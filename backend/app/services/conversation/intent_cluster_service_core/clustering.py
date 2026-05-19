"""Clustering helpers for intent clusters."""

import logging
from collections import defaultdict
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)


def load_kmeans():
    """Load sklearn KMeans lazily."""
    from sklearn.cluster import KMeans

    return KMeans


async def perform_kmeans_clustering(
    *,
    embeddings_matrix: np.ndarray,
    intent_ids: List[str],
    n_clusters: int,
) -> List[List[str]]:
    """Perform K-means clustering on embeddings."""
    try:
        n_init = 5 if len(intent_ids) > 20 else 10
        kmeans = load_kmeans()(
            n_clusters=n_clusters,
            random_state=42,
            n_init=n_init,
            max_iter=100,
        )
        cluster_labels = kmeans.fit_predict(embeddings_matrix)

        clusters: Dict[int, List[str]] = defaultdict(list)
        for idx, label in enumerate(cluster_labels):
            clusters[label].append(intent_ids[idx])

        return list(clusters.values())

    except ImportError:
        logger.warning("scikit-learn not available, using simple distance-based clustering")
        return simple_distance_clustering(embeddings_matrix, intent_ids, n_clusters)
    except Exception as exc:
        logger.error("K-means clustering failed: %s", exc, exc_info=True)
        return simple_distance_clustering(embeddings_matrix, intent_ids, n_clusters)


def simple_distance_clustering(
    embeddings_matrix: np.ndarray,
    intent_ids: List[str],
    n_clusters: int,
) -> List[List[str]]:
    """Simple distance-based clustering fallback."""
    n_intents = len(intent_ids)
    if n_intents <= n_clusters:
        return [[intent_id] for intent_id in intent_ids]

    clusters: Dict[int, List[str]] = {i: [] for i in range(n_clusters)}

    for i in range(n_clusters):
        clusters[i].append(intent_ids[i])

    for i in range(n_clusters, n_intents):
        intent_embedding = embeddings_matrix[i]
        min_dist = float("inf")
        nearest_cluster = 0

        for cluster_idx in range(n_clusters):
            center_embedding = embeddings_matrix[cluster_idx]
            dist = 1 - np.dot(intent_embedding, center_embedding) / (
                np.linalg.norm(intent_embedding) * np.linalg.norm(center_embedding)
            )
            if dist < min_dist:
                min_dist = dist
                nearest_cluster = cluster_idx

        clusters[nearest_cluster].append(intent_ids[i])

    return list(clusters.values())

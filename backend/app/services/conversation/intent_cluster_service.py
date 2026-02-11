"""
Intent Cluster Service

Handles clustering of IntentCards using embeddings for cross-turn, cross-day intent convergence.

Phase 3: Embedding clustering layer
"""

import logging
import uuid
import numpy as np
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from ...models.mindscape import IntentCard, IntentCluster
from ...services.mindscape_store import MindscapeStore
from ...services.stores.intent_clusters_store import IntentClustersStore
from ...services.conversation.intent_embedding_generator import IntentEmbeddingGenerator

logger = logging.getLogger(__name__)


class IntentClusterService:
    """
    Intent Cluster Service - Phase 3

    Clusters IntentCards by semantic similarity using embeddings.
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize Intent Cluster Service

        Args:
            store: MindscapeStore instance
        """
        self.store = store
        self.clusters_store = IntentClustersStore(db_path=store.db_path)
        self.embedding_generator = IntentEmbeddingGenerator(store=store)

    async def generate_embeddings(
        self,
        intent_cards: List[IntentCard]
    ) -> Dict[str, List[float]]:
        """
        Generate embeddings for IntentCards

        Args:
            intent_cards: List of IntentCards

        Returns:
            Dictionary mapping IntentCard ID to embedding vector
        """
        return await self.embedding_generator.generate_embeddings_batch(intent_cards)

    async def cluster_intents(
        self,
        workspace_id: str,
        profile_id: str,
        n_clusters: Optional[int] = None
    ) -> List[IntentCluster]:
        """
        Cluster IntentCards for a workspace/profile

        Args:
            workspace_id: Workspace ID
            profile_id: Profile ID
            n_clusters: Number of clusters (auto-determined if None)

        Returns:
            List of IntentClusters
        """
        try:
            logger.info(
                f"IntentClusterService: Starting clustering for "
                f"workspace={workspace_id}, profile={profile_id}"
            )

            # Get all IntentCards for this profile
            intent_cards = self.store.list_intents(profile_id=profile_id)

            # Filter to ACTIVE intents only
            active_intents = [
                intent for intent in intent_cards
                if intent.status.value == "active"
            ]

            if len(active_intents) < 2:
                logger.info("Not enough IntentCards for clustering (need at least 2)")
                return []

            logger.info(f"Generating embeddings for {len(active_intents)} IntentCards...")

            existing_clusters = self.clusters_store.list_clusters(
                workspace_id=workspace_id,
                profile_id=profile_id
            )

            intents_with_cluster = set()
            for cluster in existing_clusters:
                intents_with_cluster.update(cluster.intent_card_ids)

            intents_to_embed = [
                intent for intent in active_intents
                if intent.id not in intents_with_cluster
            ]

            if intents_to_embed:
                embeddings_dict = await self.generate_embeddings(intents_to_embed)
            else:
                embeddings_dict = {}

            if len(embeddings_dict) < 2 and len(active_intents) >= 2:
                embeddings_dict = await self.generate_embeddings(active_intents)

            if len(embeddings_dict) < 2:
                logger.warning("Not enough embeddings generated for clustering")
                return []

            # Prepare data for clustering
            intent_ids = list(embeddings_dict.keys())
            embeddings_matrix = np.array([embeddings_dict[intent_id] for intent_id in intent_ids])

            # Determine number of clusters
            if n_clusters is None:
                # Auto-determine: use sqrt of number of intents, but at least 2 and at most 10
                n_clusters = max(2, min(10, int(np.sqrt(len(intent_ids)))))

            n_clusters = min(n_clusters, len(intent_ids))

            # Perform K-means clustering
            clusters = await self._perform_kmeans_clustering(
                embeddings_matrix=embeddings_matrix,
                intent_ids=intent_ids,
                n_clusters=n_clusters
            )

            # Generate cluster labels and create IntentCluster objects
            intent_clusters = []
            for cluster_idx, cluster_intent_ids in enumerate(clusters):
                if not cluster_intent_ids:
                    continue

                cluster_intent_cards = [
                    intent for intent in active_intents
                    if intent.id in cluster_intent_ids
                ]

                # Generate cluster label using LLM
                cluster_label = await self.generate_cluster_label(
                    cluster_intent_cards=cluster_intent_cards
                )

                # Calculate cluster center (mean embedding)
                cluster_embeddings = [embeddings_dict[intent_id] for intent_id in cluster_intent_ids]
                cluster_center = np.mean(cluster_embeddings, axis=0).tolist()

                # Create IntentCluster
                cluster = IntentCluster(
                    id=str(uuid.uuid4()),
                    label=cluster_label,
                    embedding=cluster_center,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    intent_card_ids=cluster_intent_ids,
                    metadata={
                        "cluster_index": cluster_idx,
                        "intent_count": len(cluster_intent_ids),
                        "created_at": _utc_now().isoformat()
                    },
                    created_at=_utc_now(),
                    updated_at=_utc_now()
                )

                intent_clusters.append(cluster)

            # Save clusters to database
            for cluster in intent_clusters:
                # Check if cluster with same intent_card_ids already exists
                existing = self._find_existing_cluster(cluster, workspace_id, profile_id)
                if existing:
                    # Update existing cluster
                    existing.label = cluster.label
                    existing.embedding = cluster.embedding
                    existing.intent_card_ids = cluster.intent_card_ids
                    existing.metadata = cluster.metadata
                    existing.updated_at = _utc_now()
                    self.clusters_store.update_cluster(existing)
                else:
                    # Create new cluster
                    self.clusters_store.create_cluster(cluster)

            # Update IntentCard metadata with cluster_id
            await self.update_intent_card_clusters(intent_clusters)

            logger.info(
                f"IntentClusterService: Created {len(intent_clusters)} clusters "
                f"for {len(active_intents)} IntentCards"
            )

            return intent_clusters

        except Exception as e:
            logger.error(f"Failed to cluster intents: {e}", exc_info=True)
            return []

    async def _perform_kmeans_clustering(
        self,
        embeddings_matrix: np.ndarray,
        intent_ids: List[str],
        n_clusters: int
    ) -> List[List[str]]:
        """
        Perform K-means clustering on embeddings

        Args:
            embeddings_matrix: Numpy array of embeddings (n_intents, embedding_dim)
            intent_ids: List of IntentCard IDs corresponding to embeddings
            n_clusters: Number of clusters

        Returns:
            List of clusters, each containing list of IntentCard IDs
        """
        try:
            from sklearn.cluster import KMeans
            from collections import defaultdict

            n_init = 5 if len(intent_ids) > 20 else 10

            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=n_init, max_iter=100)
            cluster_labels = kmeans.fit_predict(embeddings_matrix)

            clusters: Dict[int, List[str]] = defaultdict(list)
            for idx, label in enumerate(cluster_labels):
                clusters[label].append(intent_ids[idx])

            return list(clusters.values())

        except ImportError:
            logger.warning("scikit-learn not available, using simple distance-based clustering")
            # Fallback: simple distance-based clustering
            return self._simple_distance_clustering(embeddings_matrix, intent_ids, n_clusters)
        except Exception as e:
            logger.error(f"K-means clustering failed: {e}", exc_info=True)
            return self._simple_distance_clustering(embeddings_matrix, intent_ids, n_clusters)

    def _simple_distance_clustering(
        self,
        embeddings_matrix: np.ndarray,
        intent_ids: List[str],
        n_clusters: int
    ) -> List[List[str]]:
        """
        Simple distance-based clustering fallback

        Args:
            embeddings_matrix: Numpy array of embeddings
            intent_ids: List of IntentCard IDs
            n_clusters: Number of clusters

        Returns:
            List of clusters
        """
        # Simple approach: use first n_clusters intents as cluster centers
        # and assign others to nearest center
        n_intents = len(intent_ids)
        if n_intents <= n_clusters:
            return [[intent_id] for intent_id in intent_ids]

        clusters: Dict[int, List[str]] = {i: [] for i in range(n_clusters)}

        # First n_clusters intents are cluster centers
        for i in range(n_clusters):
            clusters[i].append(intent_ids[i])

        # Assign remaining intents to nearest cluster
        for i in range(n_clusters, n_intents):
            intent_embedding = embeddings_matrix[i]
            min_dist = float('inf')
            nearest_cluster = 0

            for cluster_idx in range(n_clusters):
                center_embedding = embeddings_matrix[cluster_idx]
                # Cosine distance
                dist = 1 - np.dot(intent_embedding, center_embedding) / (
                    np.linalg.norm(intent_embedding) * np.linalg.norm(center_embedding)
                )
                if dist < min_dist:
                    min_dist = dist
                    nearest_cluster = cluster_idx

            clusters[nearest_cluster].append(intent_ids[i])

        return list(clusters.values())

    async def generate_cluster_label(
        self,
        cluster_intent_cards: List[IntentCard]
    ) -> str:
        """
        Generate cluster label using LLM

        Args:
            cluster_intent_cards: List of IntentCards in the cluster

        Returns:
            Cluster label string
        """
        try:
            if not cluster_intent_cards:
                return "Unnamed Cluster"

            # Build prompt with IntentCard titles
            titles = [intent.title for intent in cluster_intent_cards[:10]]
            titles_text = "\n".join([f"- {title}" for title in titles])

            prompt = f"""Based on the following IntentCard titles, generate a concise cluster label (2-4 words) that represents the common theme:

{titles_text}

Cluster label (2-4 words, in English, no quotes):"""

            # Call LLM to generate label
            from ...services.system_settings_store import SystemSettingsStore
            from ...shared.llm_utils import call_llm, build_prompt

            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")

            if not chat_setting or not chat_setting.value:
                # Fallback: use first intent title
                return cluster_intent_cards[0].title[:30]

            model_name = str(chat_setting.value)

            try:
                response = await call_llm(
                    prompt=build_prompt(prompt),
                    model_name=model_name,
                    temperature=0.3,
                    max_tokens=20
                )

                label = response.strip().strip('"').strip("'")
                if len(label) > 50:
                    label = label[:50]

                return label if label else cluster_intent_cards[0].title[:30]
            except Exception as e:
                logger.warning(f"Failed to generate cluster label with LLM: {e}")
                # Fallback: use first intent title
                return cluster_intent_cards[0].title[:30]

        except Exception as e:
            logger.error(f"Failed to generate cluster label: {e}", exc_info=True)
            # Fallback: use first intent title
            return cluster_intent_cards[0].title[:30] if cluster_intent_cards else "Unnamed Cluster"

    async def update_intent_card_clusters(
        self,
        clusters: List[IntentCluster]
    ):
        """
        Update IntentCard metadata with cluster_id

        Args:
            clusters: List of IntentClusters
        """
        try:
            for cluster in clusters:
                for intent_id in cluster.intent_card_ids:
                    intent = self.store.get_intent(intent_id)
                    if intent:
                        if not intent.metadata:
                            intent.metadata = {}
                        intent.metadata.update({
                            "cluster_id": cluster.id,
                            "cluster_label": cluster.label
                        })
                        intent.updated_at = _utc_now()
                        self.store.intents.update_intent(intent)

            logger.info(f"Updated {sum(len(c.intent_card_ids) for c in clusters)} IntentCards with cluster information")

        except Exception as e:
            logger.error(f"Failed to update IntentCard clusters: {e}", exc_info=True)

    def _find_existing_cluster(
        self,
        new_cluster: IntentCluster,
        workspace_id: str,
        profile_id: str
    ) -> Optional[IntentCluster]:
        """
        Find existing cluster with same intent_card_ids

        Args:
            new_cluster: New cluster to check
            workspace_id: Workspace ID
            profile_id: Profile ID

        Returns:
            Existing cluster or None
        """
        existing_clusters = self.clusters_store.list_clusters(
            workspace_id=workspace_id,
            profile_id=profile_id
        )

        new_ids_set = set(new_cluster.intent_card_ids)
        for existing in existing_clusters:
            existing_ids_set = set(existing.intent_card_ids)
            if new_ids_set == existing_ids_set:
                return existing

        return None


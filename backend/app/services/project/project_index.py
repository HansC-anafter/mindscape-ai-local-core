"""
Project Index Service

Maintains a vector index of projects for similarity search.
Each project has an embedding based on its title, summary, keywords, and recent phases.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.event_embedding_generator import EventEmbeddingGenerator

logger = logging.getLogger(__name__)


class ProjectIndex:
    """
    Project Index - maintains vector embeddings for project similarity search
    """

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.project_manager = ProjectManager(store)
        self.embedding_generator = EventEmbeddingGenerator(store=store)
        self._embedding_cache: Dict[str, List[float]] = {}

    async def update_project_index(self, project_id: str, workspace_id: str) -> None:
        """
        Update project index when project is created or updated

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
        """
        try:
            project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
            if not project:
                logger.warning(f"Project not found: {project_id}")
                return

            # Build project description for embedding
            description = await self._build_project_description(project, workspace_id)

            # Generate embedding
            embedding = await self._generate_embedding(description)
            if embedding:
                # Cache embedding
                self._embedding_cache[project_id] = embedding
                logger.info(f"Updated project index for {project_id} (embedding dimension: {len(embedding)})")
            else:
                logger.warning(f"Failed to generate embedding for project {project_id}")

        except Exception as e:
            logger.error(f"Failed to update project index for {project_id}: {e}", exc_info=True)

    async def top_k_similar(
        self,
        workspace_id: str,
        text: str,
        k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find top K similar projects using vector search

        Args:
            workspace_id: Workspace ID
            text: Query text (user message)
            k: Number of candidates to return

        Returns:
            List of project candidates with similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_embedding(text)
            if not query_embedding or len(query_embedding) == 0:
                logger.warning("Failed to generate query embedding, returning empty results")
                return []

            # Get all projects in workspace
            projects = await self.project_manager.list_projects(workspace_id, state="open")
            if not projects:
                return []

            # Calculate similarity for each project
            candidates = []
            for project in projects:
                # Get or generate project embedding
                project_embedding = await self._get_project_embedding(project.id, workspace_id)
                if not project_embedding or len(project_embedding) == 0:
                    continue

                # Calculate cosine similarity
                similarity = self._calculate_similarity(query_embedding, project_embedding)
                candidates.append({
                    "project_id": project.id,
                    "project": project,
                    "similarity": similarity
                })

            # Sort by similarity and return top K
            candidates.sort(key=lambda x: x["similarity"], reverse=True)
            return candidates[:k]

        except Exception as e:
            logger.error(f"Failed to find similar projects: {e}", exc_info=True)
            return []

    async def _build_project_description(
        self,
        project: "Project",
        workspace_id: str
    ) -> str:
        """
        Build text description for project embedding

        Args:
            project: Project object
            workspace_id: Workspace ID

        Returns:
            Text description for embedding
        """
        parts = [
            f"Title: {project.title}",
            f"Type: {project.type}",
        ]

        # Add summary if available in metadata
        if project.metadata and project.metadata.get("summary"):
            parts.append(f"Summary: {project.metadata.get('summary')}")

        # Add keywords if available in metadata
        if project.metadata and project.metadata.get("keywords"):
            keywords = project.metadata.get("keywords")
            if isinstance(keywords, list):
                parts.append(f"Keywords: {', '.join(keywords)}")
            elif isinstance(keywords, str):
                parts.append(f"Keywords: {keywords}")

        # Add recent phases summary if available
        try:
            from backend.app.services.project.project_phase_manager import ProjectPhaseManager
            phase_manager = ProjectPhaseManager(store=self.store)
            recent_phases = await phase_manager.get_recent_phases(project_id=project.id, limit=3)
            if recent_phases:
                phase_summaries = [f"- {p.kind}: {p.summary[:50]}" for p in recent_phases]
                parts.append(f"Recent phases:\n" + "\n".join(phase_summaries))
        except Exception as e:
            logger.debug(f"Failed to load recent phases for project {project.id}: {e}")

        return "\n".join(parts)

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if generation failed
        """
        try:
            # Reuse EventEmbeddingGenerator's embedding generation logic
            embedding = await self.embedding_generator._generate_embedding(text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            return None

    async def _get_project_embedding(
        self,
        project_id: str,
        workspace_id: str
    ) -> List[float]:
        """
        Get cached project embedding or generate new one

        Args:
            project_id: Project ID
            workspace_id: Workspace ID

        Returns:
            Embedding vector or empty list if failed
        """
        # Check cache first
        if project_id in self._embedding_cache:
            return self._embedding_cache[project_id]

        # Generate and cache embedding
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            return []

        description = await self._build_project_description(project, workspace_id)
        embedding = await self._generate_embedding(description)
        if embedding:
            self._embedding_cache[project_id] = embedding
            return embedding

        return []

    def _calculate_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score (0-1)
        """
        try:
            # Convert to numpy arrays
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)

            # Check if dimensions match
            if len(vec1) != len(vec2):
                logger.warning(f"Embedding dimensions mismatch: {len(vec1)} vs {len(vec2)}")
                return 0.0

            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            # Normalize to [0, 1] range (cosine similarity is already in [-1, 1])
            return float((similarity + 1) / 2)

        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}", exc_info=True)
            return 0.0


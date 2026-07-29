"""
Content Vault Indexer Service

Provides vector indexing for Content Vault documents to enable semantic search.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import re

from backend.app.services.vector_search import VectorSearchService
from backend.app.services.knowledge_authorization import RetrievalAccessContext
from backend.app.services.knowledge_projection.legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
    LegacyDocumentChunk,
)
from backend.app.services.knowledge_projection.retrievable.canonical_json import (
    canonical_sha256,
)

logger = logging.getLogger(__name__)


class ContentVaultIndexer:
    """
    Content Vault vector indexing service

    Indexes Content Vault documents (Series, Arcs, Posts) into vector database
    for semantic search capabilities.
    """

    def __init__(
        self,
        vector_service: Optional[VectorSearchService] = None,
        *,
        workspace_id: Optional[str] = None,
        access_context: Optional[RetrievalAccessContext] = None,
    ):
        self.vector_service = vector_service or VectorSearchService()
        self.workspace_id = workspace_id
        self.access_context = access_context
        self.projection_facade = AuthorizedLegacyDocumentFacade(
            vector_service=self.vector_service
        )

    def _parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        """
        Parse YAML frontmatter from markdown content

        Args:
            content: Markdown content with frontmatter

        Returns:
            Tuple of (frontmatter dict, body text)
        """
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if match:
            frontmatter_str = match.group(1)
            body = match.group(2)
            try:
                frontmatter = yaml.safe_load(frontmatter_str) or {}
                return frontmatter, body
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse frontmatter: {e}")
                return {}, content
        else:
            return {}, content

    def _load_posts_by_series(
        self,
        vault_path: Path,
        series_id: str
    ) -> List[Dict[str, Any]]:
        """
        Load all posts for a specific series

        Args:
            vault_path: Path to content vault
            series_id: Series ID to load posts for

        Returns:
            List of post dictionaries
        """
        posts = []
        posts_dir = vault_path / "posts" / "instagram"

        if not posts_dir.exists():
            logger.warning(f"Posts directory not found: {posts_dir}")
            return posts

        for post_file in posts_dir.glob("*.md"):
            try:
                content = post_file.read_text(encoding='utf-8')
                frontmatter, body = self._parse_frontmatter(content)

                if frontmatter.get('series_id') == series_id:
                    posts.append({
                        'id': post_file.stem,
                        'series_id': series_id,
                        'arc_id': frontmatter.get('arc_id'),
                        'sequence': frontmatter.get('sequence'),
                        'text': body.strip(),
                        'title': frontmatter.get('title', post_file.stem),
                        'status': frontmatter.get('status', 'draft'),
                        'file_path': str(post_file.relative_to(vault_path)),
                        'frontmatter': frontmatter,
                    })
            except Exception as e:
                logger.error(f"Failed to load post {post_file}: {e}")

        posts.sort(key=lambda p: p.get('sequence', 0))
        return posts

    def _chunk_post(self, post: Dict[str, Any], max_len: int = 500) -> List[Dict[str, Any]]:
        """
        Chunk post text if it exceeds max length

        Args:
            post: Post dictionary
            max_len: Maximum chunk length

        Returns:
            List of chunk dictionaries
        """
        text = post.get('text', '')
        if len(text) <= max_len:
            return [post]

        chunks = []
        paragraphs = text.split('\n\n')
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) > max_len:
                if current_chunk:
                    chunks.append({
                        **post,
                        'text': current_chunk.strip(),
                        'chunk_index': len(chunks)
                    })
                current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        if current_chunk:
            chunks.append({
                **post,
                'text': current_chunk.strip(),
                'chunk_index': len(chunks)
            })

        return chunks

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector or None if generation fails
        """
        return await self.vector_service._generate_embedding(text)

    async def index_series(
        self,
        vault_path: str,
        series_id: str,
    ) -> Dict[str, Any]:
        """
        Index all posts for a specific series

        Args:
            vault_path: Path to content vault
            series_id: Series ID to index
            user_id: User ID for indexing

        Returns:
            Dictionary with indexing results
        """
        vault_path = Path(vault_path).expanduser().resolve()

        if not vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        posts = self._load_posts_by_series(vault_path, series_id)

        if not posts:
            logger.warning(f"No posts found for series: {series_id}")
            return {
                'status': 'success',
                'series_id': series_id,
                'posts_indexed': 0,
                'chunks_indexed': 0
            }

        indexed_count = 0
        failed_count = 0
        if self.workspace_id is None or self.access_context is None:
            raise PermissionError("content_vault_authorized_scope_required")
        for post in posts:
            try:
                chunks = self._chunk_post(post)
                await self.projection_facade.replace_document(
                    access_context=self.access_context,
                    workspace_id=self.workspace_id,
                    owner_capability_code="content_vault",
                    source_app="content-vault",
                    source_id=f"{series_id}:{post['id']}",
                    doc_type="content_vault_post",
                    source_revision=canonical_sha256(
                        {
                            "post": post,
                            "chunks": [chunk["text"] for chunk in chunks],
                        }
                    ),
                    chunks=tuple(
                        LegacyDocumentChunk(
                            content=chunk["text"],
                            title=chunk.get("title", "Untitled"),
                            metadata={
                                "series_id": series_id,
                                "arc_id": chunk.get("arc_id"),
                                "sequence": chunk.get("sequence"),
                                "file_path": chunk.get("file_path"),
                                "post_id": chunk.get("id"),
                                "chunk_index": chunk.get("chunk_index", 0),
                                "status": chunk.get("status", "draft"),
                            },
                        )
                        for chunk in chunks
                    ),
                )
                indexed_count += len(chunks)
            except Exception as e:
                logger.error(f"Failed to index chunk: {e}")
                failed_count += 1

        return {
            'status': 'success',
            'series_id': series_id,
            'posts_indexed': len(posts),
            'chunks_indexed': indexed_count,
            'failed': failed_count
        }

    async def index_all_series(
        self,
        vault_path: str,
    ) -> Dict[str, Any]:
        """
        Index all series in the vault

        Args:
            vault_path: Path to content vault
            user_id: User ID for indexing

        Returns:
            Dictionary with indexing results
        """
        vault_path = Path(vault_path).expanduser().resolve()
        series_dir = vault_path / "series"

        if not series_dir.exists():
            logger.warning(f"Series directory not found: {series_dir}")
            return {
                'status': 'success',
                'series_indexed': 0,
                'total_posts': 0,
                'total_chunks': 0
            }

        series_files = list(series_dir.glob("*.md"))
        total_posts = 0
        total_chunks = 0

        for series_file in series_files:
            try:
                content = series_file.read_text(encoding='utf-8')
                frontmatter, _ = self._parse_frontmatter(content)
                series_id = frontmatter.get('series_id') or series_file.stem

                result = await self.index_series(vault_path, series_id)
                total_posts += result.get('posts_indexed', 0)
                total_chunks += result.get('chunks_indexed', 0)
            except Exception as e:
                logger.error(f"Failed to index series {series_file}: {e}")

        return {
            'status': 'success',
            'series_indexed': len(series_files),
            'total_posts': total_posts,
            'total_chunks': total_chunks
        }





"""
WordPress Sync Service
Syncs WordPress posts and pages to pgvector for RAG
"""

import os
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Dict, Any, Optional
import psycopg2
import requests
from html import unescape
import re

from backend.app.services.knowledge_authorization import RetrievalAccessContext
from backend.app.services.knowledge_projection.legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
    LegacyDocumentChunk,
)
from backend.app.services.knowledge_projection.retrievable.canonical_json import (
    canonical_sha256,
)

logger = logging.getLogger(__name__)


class WordPressSync:
    """Sync WordPress content to vector database"""

    def __init__(
        self,
        *,
        workspace_id: str | None = None,
        access_context: RetrievalAccessContext | None = None,
        projection_facade: AuthorizedLegacyDocumentFacade | None = None,
    ):
        self.workspace_id = workspace_id
        self.access_context = access_context
        self.projection_facade = (
            projection_facade or AuthorizedLegacyDocumentFacade()
        )

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI"""
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                logger.warning("OPENAI_API_KEY not set")
                return None

            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000]  # Limit to avoid token limit
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def _clean_html(self, html_content: str) -> str:
        """Clean HTML tags and decode entities"""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)
        # Decode HTML entities
        text = unescape(text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    async def sync_posts(
        self,
        site_url: str,
        post_types: List[str] = None,
        per_page: int = 10
    ) -> Dict[str, Any]:
        """
        Sync WordPress posts from REST API

        Args:
            site_url: WordPress site URL
            user_id: User identifier
            post_types: Post types to sync (default: ['post', 'page'])
            per_page: Posts per page

        Returns:
            Sync statistics
        """
        if post_types is None:
            post_types = ['post', 'page']

        stats = {
            "total_fetched": 0,
            "new": 0,
            "updated": 0,
            "skipped": 0,
            "failed": []
        }

        for post_type in post_types:
            try:
                # Fetch posts from WordPress REST API
                api_url = f"{site_url}/wp-json/wp/v2/{post_type}s"
                params = {
                    'per_page': per_page,
                    'orderby': 'modified',
                    'order': 'desc',
                    '_embed': 1  # Include embedded data (author, featured image, etc.)
                }

                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()

                posts = response.json()
                stats["total_fetched"] += len(posts)

                logger.info(f"Fetched {len(posts)} {post_type}s from {site_url}")

                # Sync each post
                for post in posts:
                    try:
                        result = await self.sync_single_post(
                            post=post,
                            site_url=site_url,
                            doc_type=post_type
                        )

                        if result == "new":
                            stats["new"] += 1
                        elif result == "updated":
                            stats["updated"] += 1
                        elif result == "skipped":
                            stats["skipped"] += 1

                    except Exception as e:
                        logger.error(f"Failed to sync post {post.get('id')}: {e}")
                        stats["failed"].append({
                            "post_id": post.get('id'),
                            "title": post.get('title', {}).get('rendered', 'Unknown'),
                            "error": str(e)
                        })

            except requests.RequestException as e:
                logger.error(f"Failed to fetch {post_type}s from {site_url}: {e}")
                stats["failed"].append({
                    "post_type": post_type,
                    "error": str(e)
                })

        logger.info(f"WordPress sync complete: {stats['new']} new, {stats['updated']} updated, {stats['skipped']} skipped")
        return stats

    async def sync_single_post(
        self,
        post: Dict[str, Any],
        site_url: str,
        doc_type: str = "post"
    ) -> str:
        """
        Sync a single WordPress post

        Args:
            post: WordPress post data from REST API
            site_url: WordPress site URL
            user_id: User identifier
            doc_type: Document type (post/page)

        Returns:
            "new", "updated", or "skipped"
        """
        post_id = str(post.get('id'))
        source_id = f"wp_{post_id}"

        # Extract post data
        title = post.get('title', {}).get('rendered', '')
        content_html = post.get('content', {}).get('rendered', '')
        excerpt = post.get('excerpt', {}).get('rendered', '')
        modified = post.get('modified', '')
        link = post.get('link', '')

        # Clean HTML
        title_clean = self._clean_html(title)
        content_clean = self._clean_html(content_html)
        excerpt_clean = self._clean_html(excerpt)

        if self.workspace_id is None or self.access_context is None:
            raise PermissionError("wordpress_authorized_scope_required")

        try:
            modified_dt = datetime.fromisoformat(modified.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            modified_dt = _utc_now()

        revision = canonical_sha256(
            {
                "site_url": site_url,
                "source_id": source_id,
                "modified": modified_dt.isoformat(),
                "title": title_clean,
                "content": content_clean,
                "excerpt": excerpt_clean,
            }
        )
        existing_revision = self.projection_facade.active_revision(
            access_context=self.access_context,
            workspace_id=self.workspace_id,
            owner_capability_code="wordpress",
            source_app="wordpress",
            source_id=source_id,
        )
        if existing_revision == revision:
            logger.debug(
                "Post %s not modified since last sync, skipping",
                post_id,
            )
            return "skipped"

        full_text = f"{title_clean}\n\n{excerpt_clean}\n\n{content_clean}"
        embedding_text = full_text[:8000]

        embedding = await self._generate_embedding(embedding_text)

        if not embedding:
            logger.warning(
                "Failed to generate embedding for post %s, skipping",
                post_id,
            )
            return "skipped"

        metadata = {
            "url": link,
            "author": post.get('author'),
            "publish_date": post.get('date', ''),
            "modified_date": modified,
            "excerpt": excerpt_clean[:500],
            "categories": post.get('categories', []),
            "tags": post.get('tags', []),
            "status": post.get('status', 'publish'),
            "embedding_model": "text-embedding-3-small",
        }

        await self.projection_facade.replace_document(
            access_context=self.access_context,
            workspace_id=self.workspace_id,
            owner_capability_code="wordpress",
            source_app="wordpress",
            source_id=source_id,
            doc_type=doc_type,
            source_revision=revision,
            chunks=(
                LegacyDocumentChunk(
                    content=content_clean,
                    title=title_clean,
                    metadata=metadata,
                    embedding=tuple(embedding),
                ),
            ),
        )
        state = "updated" if existing_revision else "new"
        logger.info(
            "%s WordPress %s %s: %s",
            state,
            doc_type,
            post_id,
            title_clean,
        )
        return state

    async def delete_post(
        self,
        source_id: str,
    ) -> bool:
        """
        Delete a synced post from vector database

        Args:
            source_id: WordPress post ID (e.g., "wp_123")
            user_id: User identifier

        Returns:
            True if deleted, False if not found
        """
        if self.workspace_id is None or self.access_context is None:
            raise PermissionError("wordpress_authorized_scope_required")
        result = self.projection_facade.revoke_document(
            access_context=self.access_context,
            workspace_id=self.workspace_id,
            owner_capability_code="wordpress",
            source_app="wordpress",
            source_id=source_id,
        )
        if result is None:
            logger.warning("WordPress post %s not found", source_id)
            return False
        logger.info("Revoked WordPress post %s", source_id)
        return True

    async def list_synced_posts(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List synced WordPress posts

        Args:
            user_id: User identifier
            limit: Maximum number of posts

        Returns:
            List of synced posts
        """
        if self.workspace_id is None or self.access_context is None:
            raise PermissionError("wordpress_authorized_scope_required")
        return self.projection_facade.list_documents(
            access_context=self.access_context,
            workspace_id=self.workspace_id,
            owner_capability_code="wordpress",
            source_app="wordpress",
            limit=limit,
        )

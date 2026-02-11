"""
WordPress Sync Service
Syncs WordPress posts and pages to pgvector for RAG
"""

import os
import uuid
import json
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from html import unescape
import re

from app.database.config import get_vector_postgres_config

logger = logging.getLogger(__name__)


class WordPressSync:
    """Sync WordPress content to vector database"""

    def __init__(self, postgres_config=None):
        self.postgres_config = postgres_config or self._get_postgres_config()

    def _get_postgres_config(self):
        """Get PostgreSQL config from environment"""
        return get_vector_postgres_config()

    def _get_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(**self.postgres_config)

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
        user_id: str = "default_user",
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
                            user_id=user_id,
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
        user_id: str = "default_user",
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

        # Check if post exists and needs update
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute('''
                SELECT id, updated_at, last_synced_at
                FROM external_docs
                WHERE user_id = %s AND source_app = 'wordpress' AND source_id = %s
            ''', (user_id, source_id))

            existing = cursor.fetchone()

            # Parse modified date
            try:
                modified_dt = datetime.fromisoformat(modified.replace('Z', '+00:00'))
            except:
                modified_dt = _utc_now()

            # Skip if not modified since last sync
            if existing:
                last_synced = existing['last_synced_at']
                if last_synced and modified_dt <= last_synced:
                    logger.debug(f"Post {post_id} not modified since last sync, skipping")
                    return "skipped"

            # Prepare content for embedding (title + excerpt + content, truncated)
            full_text = f"{title_clean}\n\n{excerpt_clean}\n\n{content_clean}"
            embedding_text = full_text[:8000]  # Limit for embedding API

            # Generate embedding
            embedding = await self._generate_embedding(embedding_text)

            if not embedding:
                logger.warning(f"Failed to generate embedding for post {post_id}, skipping")
                return "skipped"

            # Prepare metadata
            metadata = {
                "url": link,
                "author": post.get('author'),
                "publish_date": post.get('date', ''),
                "modified_date": modified,
                "excerpt": excerpt_clean[:500],
                "categories": post.get('categories', []),
                "tags": post.get('tags', []),
                "status": post.get('status', 'publish')
            }

            # Upsert to database
            if existing:
                # Update existing
                cursor.execute('''
                    UPDATE external_docs
                    SET title = %s,
                        content = %s,
                        embedding = %s::vector,
                        metadata = %s,
                        updated_at = %s,
                        last_synced_at = NOW()
                    WHERE id = %s
                ''', (
                    title_clean,
                    content_clean,
                    str(embedding),
                    json.dumps(metadata),
                    modified_dt,
                    existing['id']
                ))
                conn.commit()
                logger.info(f"Updated WordPress {doc_type} {post_id}: {title_clean}")
                return "updated"
            else:
                # Insert new
                doc_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO external_docs (
                        id, user_id, source_app, source_id, doc_type,
                        title, content, embedding, metadata,
                        created_at, updated_at, last_synced_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, NOW())
                ''', (
                    doc_id,
                    user_id,
                    'wordpress',
                    source_id,
                    doc_type,
                    title_clean,
                    content_clean,
                    str(embedding),
                    json.dumps(metadata),
                    modified_dt,
                    modified_dt
                ))
                conn.commit()
                logger.info(f"Inserted new WordPress {doc_type} {post_id}: {title_clean}")
                return "new"

        finally:
            conn.close()

    async def delete_post(
        self,
        source_id: str,
        user_id: str = "default_user"
    ) -> bool:
        """
        Delete a synced post from vector database

        Args:
            source_id: WordPress post ID (e.g., "wp_123")
            user_id: User identifier

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM external_docs
                WHERE user_id = %s AND source_app = 'wordpress' AND source_id = %s
            ''', (user_id, source_id))

            deleted = cursor.rowcount > 0
            conn.commit()

            if deleted:
                logger.info(f"Deleted WordPress post {source_id}")
            else:
                logger.warning(f"WordPress post {source_id} not found")

            return deleted

        finally:
            conn.close()

    async def list_synced_posts(
        self,
        user_id: str = "default_user",
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
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute('''
                SELECT
                    id, source_id, doc_type, title,
                    metadata, created_at, updated_at, last_synced_at
                FROM external_docs
                WHERE user_id = %s AND source_app = 'wordpress'
                ORDER BY last_synced_at DESC
                LIMIT %s
            ''', (user_id, limit))

            posts = cursor.fetchall()
            return [dict(post) for post in posts]

        finally:
            conn.close()

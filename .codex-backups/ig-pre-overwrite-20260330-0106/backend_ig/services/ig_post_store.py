import logging
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from sqlalchemy import text
from app.services.stores.postgres_base import PostgresStoreBase
import json

logger = logging.getLogger(__name__)


class IGPostStore(ABC):
    """Interface for IG Post storage metadata."""

    @abstractmethod
    def index_post(self, workspace_id: str, post_data: Dict[str, Any]) -> str:
        """Index post metadata to DB."""
        pass

    @abstractmethod
    def get_post_by_slug(
        self, workspace_id: str, slug: str
    ) -> Optional[Dict[str, Any]]:
        """Get post metadata by slug."""
        pass


class PostgresIGPostStore(PostgresStoreBase, IGPostStore):
    """Postgres implementation of IGPostStore."""

    def index_post(self, workspace_id: str, post_data: Dict[str, Any]) -> str:
        """
        Index post metadata to ig_posts table.
        """
        import uuid

        post_id = post_data.get("id") or str(uuid.uuid4())

        # Prepare params
        params = {
            "id": post_id,
            "workspace_id": workspace_id,
            "post_slug": post_data.get("slug"),
            "title": post_data.get("title"),
            "post_type": post_data.get("type", "post"),
            "status": post_data.get("status", "draft"),
            "scheduled_at": post_data.get("scheduled_at"),
            "published_at": post_data.get("published_at"),
            "platform_id": post_data.get("platform_id"),
            "permalink": post_data.get("permalink"),
            "caption": post_data.get("caption"),
            "hashtags": json.dumps(post_data.get("hashtags", [])),
            "metrics": json.dumps(post_data.get("metrics", {})),
            "metadata": json.dumps(post_data.get("metadata", {})),
            "updated_at": _utc_now().isoformat(),  # Always update timestamp
        }

        with self.transaction() as conn:
            # Upsert logic (PostgreSQL style)
            query = text(
                """
                INSERT INTO ig_posts (
                    id, workspace_id, post_slug, title, post_type, status,
                    scheduled_at, published_at, platform_id, permalink,
                    caption, hashtags, metrics, metadata, updated_at
                ) VALUES (
                    :id, :workspace_id, :post_slug, :title, :post_type, :status,
                    :scheduled_at, :published_at, :platform_id, :permalink,
                    :caption, :hashtags, :metrics, :metadata, :updated_at
                )
                ON CONFLICT (workspace_id, post_slug) DO UPDATE SET
                    title = EXCLUDED.title,
                    post_type = EXCLUDED.post_type,
                    status = EXCLUDED.status,
                    scheduled_at = EXCLUDED.scheduled_at,
                    published_at = EXCLUDED.published_at,
                    platform_id = EXCLUDED.platform_id,
                    permalink = EXCLUDED.permalink,
                    caption = EXCLUDED.caption,
                    hashtags = EXCLUDED.hashtags,
                    metrics = EXCLUDED.metrics,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
            """
            )
            conn.execute(query, params)
            logger.info(f"Indexed IG Post: {params['post_slug']}")

        return post_id

    def get_post_by_slug(
        self, workspace_id: str, slug: str
    ) -> Optional[Dict[str, Any]]:
        """Get post by slug."""
        with self.get_connection() as conn:
            query = text(
                """
                SELECT * FROM ig_posts
                WHERE workspace_id = :workspace_id AND post_slug = :slug
            """
            )
            result = conn.execute(
                query, {"workspace_id": workspace_id, "slug": slug}
            ).fetchone()

            if not result:
                return None

            row = result._mapping
            return dict(row)

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

from capabilities.ig.services.confirmed_targets import upsert_confirmed_target_handles

logger = logging.getLogger(__name__)


class IGAccountStore(ABC):
    """Interface for IG Account storage."""

    @abstractmethod
    def save_snapshot(self, snapshot_data: Dict[str, Any]) -> str:
        """Save account snapshot and return ID."""
        pass

    @abstractmethod
    def get_latest_snapshot(
        self, handle: str, workspace_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get latest snapshot for an account."""
        pass


class PostgresIGAccountStore(PostgresStoreBase, IGAccountStore):
    """Postgres implementation of IGAccountStore."""

    def save_snapshot(self, snapshot_data: Dict[str, Any]) -> str:
        """
        Save account snapshot to ig_accounts_flat table.
        """
        import uuid

        # Flatten dictionary for SQL insert
        profile = snapshot_data.get("profile", {})
        metadata = snapshot_data.get("metadata", {})
        target = snapshot_data.get("target", {})

        # Handle "N/A" or None values safely
        def safe_int(val):
            if val is None or val == "N/A":
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        # Determine Unique Logical Key for upsert prevention or id generation
        record_id = str(uuid.uuid4())

        # Prepare parameters matching SQLAlchemy model columns
        params = {
            "id": record_id,
            "workspace_id": metadata.get("workspace_id", "unknown"),
            "seed": metadata.get("source_account_handle", "unknown"),
            "source_handle": metadata.get("source_account_handle"),
            "source_profile_ref": metadata.get("source_profile_ref"),
            "handle": target.get("handle") or profile.get("username", "unknown"),
            "name": profile.get("name"),
            "is_verified": profile.get("is_verified", False),
            "follower_count": safe_int(profile.get("follower_count")),
            "following_count": safe_int(profile.get("following_count")),
            "post_count": safe_int(profile.get("post_count")),
            "bio": profile.get("bio"),
            "external_url": profile.get("external_url"),
            "profile_picture_url": profile.get("avatar_url"),
            "category": profile.get("category"),
            "tags_json": json.dumps(profile.get("tags", [])),
            "captured_at": metadata.get("captured_at") or _utc_now().isoformat(),
            "execution_id": metadata.get("execution_id"),
            "trace_id": metadata.get("trace_id"),
            "artifact_id": metadata.get("artifact_id"),
            "schema_version": "1.0",
            "seed_version": "1.0",
            "capture_method": metadata.get("source", "unknown"),
            "run_mode": "production",
        }

        with self.transaction() as conn:
            # Check for existing duplicate to be safe?
            # The migration has a unique constraint: workspace_id, seed, handle, captured_at
            # We will use INSERT ... ON CONFLICT DO UPDATE if strictly needed,
            # but snapshot implies strictly new point-in-time data usually.
            # For robustness, we'll try standard INSERT first.

            query = text(
                """
                INSERT INTO ig_accounts_flat (
                    id, workspace_id, seed, source_handle, source_profile_ref,
                    handle, name, is_verified, follower_count, following_count,
                    post_count, bio, external_url, profile_picture_url, category,
                    tags_json, captured_at, execution_id, trace_id, artifact_id,
                    schema_version, seed_version, capture_method, run_mode
                ) VALUES (
                    :id, :workspace_id, :seed, :source_handle, :source_profile_ref,
                    :handle, :name, :is_verified, :follower_count, :following_count,
                    :post_count, :bio, :external_url, :profile_picture_url, :category,
                    :tags_json, :captured_at, :execution_id, :trace_id, :artifact_id,
                    :schema_version, :seed_version, :capture_method, :run_mode
                )
            """
            )
            conn.execute(query, params)
            upsert_confirmed_target_handles(
                conn,
                workspace_id=params["workspace_id"],
                handles=[params["handle"]],
            )
            logger.info(f"Saved IG Account snapshot: {params['handle']}")

        return record_id

    def get_latest_snapshot(
        self, handle: str, workspace_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get latest snapshot ordered by captured_at DESC."""
        with self.get_connection() as conn:
            query = text(
                """
                SELECT * FROM ig_accounts_flat
                WHERE handle = :handle AND workspace_id = :workspace_id
                ORDER BY captured_at DESC
                LIMIT 1
            """
            )
            result = conn.execute(
                query, {"handle": handle, "workspace_id": workspace_id}
            ).fetchone()

            if not result:
                return None

            # Reconstruct dictionary to match tool output format roughly
            row = result._mapping
            return {
                "id": row["id"],
                "target": {
                    "handle": row["handle"],
                    "external_url": row["external_url"],
                },
                "profile": {
                    "name": row["name"],
                    "bio": row["bio"],
                    "follower_count": row["follower_count"],
                    "following_count": row["following_count"],
                    "post_count": row["post_count"],
                    "is_verified": row["is_verified"],
                    "avatar_url": row["profile_picture_url"],
                },
                "metadata": {
                    "captured_at": row["captured_at"],
                    "execution_id": row["execution_id"],
                },
            }

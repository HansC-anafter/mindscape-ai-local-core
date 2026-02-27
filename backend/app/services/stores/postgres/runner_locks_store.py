"""PostgreSQL implementation of RunnerLocksStore."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PostgresRunnerLocksStore(PostgresStoreBase):
    """Postgres implementation of RunnerLocksStore.

    The runner_locks table already exists via Alembic migration.
    No ensure_table() needed — schema is managed by Alembic.
    """

    def try_acquire(self, lock_key: str, owner_id: str, ttl_seconds: int) -> bool:
        """Try to acquire a lock. Returns True if successful."""
        if not lock_key or not owner_id:
            return False
        ttl_seconds = max(1, int(ttl_seconds))

        now = _utc_now()
        expires_at = now + timedelta(seconds=ttl_seconds)

        with self.transaction() as conn:
            # Clean expired locks
            conn.execute(
                text("DELETE FROM runner_locks WHERE expires_at < :now"),
                {"now": now},
            )

            # Try insert (new lock)
            result = conn.execute(
                text(
                    """
                    INSERT INTO runner_locks (lock_key, owner_id, expires_at, created_at, updated_at)
                    VALUES (:lock_key, :owner_id, :expires_at, :now, :now)
                    ON CONFLICT (lock_key) DO NOTHING
                """
                ),
                {
                    "lock_key": lock_key,
                    "owner_id": owner_id,
                    "expires_at": expires_at,
                    "now": now,
                },
            )
            if result.rowcount == 1:
                return True

            # Lock exists but may be expired — try to take over
            result = conn.execute(
                text(
                    """
                    UPDATE runner_locks
                    SET owner_id = :owner_id, expires_at = :expires_at, updated_at = :now
                    WHERE lock_key = :lock_key AND expires_at < :now
                """
                ),
                {
                    "owner_id": owner_id,
                    "expires_at": expires_at,
                    "now": now,
                    "lock_key": lock_key,
                },
            )
            return result.rowcount == 1

    def renew(self, lock_key: str, owner_id: str, ttl_seconds: int) -> None:
        """Renew a lock's TTL if owned by owner_id."""
        if not lock_key or not owner_id:
            return
        ttl_seconds = max(1, int(ttl_seconds))

        now = _utc_now()
        expires_at = now + timedelta(seconds=ttl_seconds)

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE runner_locks
                    SET expires_at = :expires_at, updated_at = :now
                    WHERE lock_key = :lock_key AND owner_id = :owner_id
                """
                ),
                {
                    "expires_at": expires_at,
                    "now": now,
                    "lock_key": lock_key,
                    "owner_id": owner_id,
                },
            )

    def release(self, lock_key: str, owner_id: str) -> None:
        """Release a lock if owned by owner_id."""
        if not lock_key or not owner_id:
            return
        with self.transaction() as conn:
            conn.execute(
                text(
                    "DELETE FROM runner_locks "
                    "WHERE lock_key = :lock_key AND owner_id = :owner_id"
                ),
                {"lock_key": lock_key, "owner_id": owner_id},
            )

    def get_owner(self, lock_key: str) -> Optional[str]:
        """Get the current owner of a lock, or None if expired/missing."""
        if not lock_key:
            return None
        now = _utc_now()
        with self.get_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT owner_id, expires_at FROM runner_locks "
                    "WHERE lock_key = :lock_key"
                ),
                {"lock_key": lock_key},
            )
            row = result.fetchone()
            if not row:
                return None
            if row.expires_at and row.expires_at < now:
                return None
            return row.owner_id

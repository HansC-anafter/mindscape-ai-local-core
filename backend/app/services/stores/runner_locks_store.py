import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.app.services.stores.base import StoreBase

logger = logging.getLogger(__name__)


class RunnerLocksStore(StoreBase):
    def ensure_table(self) -> None:
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS runner_locks (
                    lock_key TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def try_acquire(self, lock_key: str, owner_id: str, ttl_seconds: int) -> bool:
        if not lock_key or not owner_id:
            return False
        ttl_seconds = max(1, int(ttl_seconds))

        now = datetime.utcnow()
        now_iso = self.to_isoformat(now)
        expires_iso = self.to_isoformat(now + timedelta(seconds=ttl_seconds))

        with self.transaction() as conn:
            cursor = conn.cursor()
            self.ensure_table()

            cursor.execute("DELETE FROM runner_locks WHERE expires_at < ?", (now_iso,))

            cursor.execute(
                """
                INSERT OR IGNORE INTO runner_locks (lock_key, owner_id, expires_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lock_key, owner_id, expires_iso, now_iso, now_iso),
            )
            if cursor.rowcount == 1:
                return True

            cursor.execute(
                """
                UPDATE runner_locks
                SET owner_id = ?, expires_at = ?, updated_at = ?
                WHERE lock_key = ? AND expires_at < ?
                """,
                (owner_id, expires_iso, now_iso, lock_key, now_iso),
            )
            return cursor.rowcount == 1

    def renew(self, lock_key: str, owner_id: str, ttl_seconds: int) -> None:
        if not lock_key or not owner_id:
            return
        ttl_seconds = max(1, int(ttl_seconds))

        now = datetime.utcnow()
        now_iso = self.to_isoformat(now)
        expires_iso = self.to_isoformat(now + timedelta(seconds=ttl_seconds))

        with self.transaction() as conn:
            cursor = conn.cursor()
            self.ensure_table()
            cursor.execute(
                """
                UPDATE runner_locks
                SET expires_at = ?, updated_at = ?
                WHERE lock_key = ? AND owner_id = ?
                """,
                (expires_iso, now_iso, lock_key, owner_id),
            )

    def release(self, lock_key: str, owner_id: str) -> None:
        if not lock_key or not owner_id:
            return
        with self.transaction() as conn:
            cursor = conn.cursor()
            self.ensure_table()
            cursor.execute(
                "DELETE FROM runner_locks WHERE lock_key = ? AND owner_id = ?",
                (lock_key, owner_id),
            )

    def get_owner(self, lock_key: str) -> Optional[str]:
        if not lock_key:
            return None
        now_iso = self.to_isoformat(datetime.utcnow())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                self.ensure_table()
            except Exception:
                pass
            cursor.execute(
                "SELECT owner_id, expires_at FROM runner_locks WHERE lock_key = ?",
                (lock_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            try:
                expires_at = row["expires_at"]
                if expires_at and expires_at < now_iso:
                    return None
                return row["owner_id"]
            except Exception:
                return None


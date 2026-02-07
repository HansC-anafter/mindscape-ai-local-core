import logging
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import text
from app.database.connection_factory import ConnectionFactory

logger = logging.getLogger(__name__)


class PostgresStoreBase:
    """
    PostgreSQL-compatible store base class.
    Intended to replace Sqlite-based StoreBase for migrated groups.
    Uses SQLAlchemy mechanisms provided by ConnectionFactory.
    """

    def __init__(self, db_role: str = "core"):
        # Postgres connections are pooled globally, so we don't store a 'db_path'
        self.db_role = db_role
        self.factory = ConnectionFactory()

    @contextmanager
    def get_connection(self):
        """
        Yields a SQLAlchemy Connection object.
        Note: This API differs slightly from sqlite3 (no cursor() needed for execute).
        Adapters or refactored stores should use `conn.execute(text(...))`
        """
        conn = self.factory.get_connection(role=self.db_role)
        # If factory returns sqlite3 connection (shouldn't happen if migration is correct), handle specific error
        if self.factory.get_db_type(self.db_role) != "postgres":
            logger.warning(
                "PostgresStoreBase is running with a non-Postgres connection!"
            )

        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """
        Executes a transaction block.
        SQLAlchemy connections usually require explicit commit.
        """
        with self.get_connection() as conn:
            trans = conn.begin()
            try:
                yield conn
                trans.commit()
            except Exception as e:
                trans.rollback()
                logger.error(f"Postgres transaction rolled back: {e}")
                raise

    def serialize_json(self, data: Any) -> Optional[str]:
        """
        Serialize data to JSON string (compatible with JSONB if needed,
        though SQLAlchemy handles JSONB automatically if using ORM/Core types).
        For raw SQL text queries, we still often need to pass stringified JSON
        unless using bind params with specific types.
        """
        if data is None:
            return None
        try:
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize JSON: {e}")
            raise ValueError(f"Invalid JSON data: {e}")

    def deserialize_json(self, data: Any, default: Any = None) -> Any:
        """
        Deserialize JSON.
        Postgres driver (psycopg2) might return dict automatically for JSONB columns,
        or string for TEXT columns. This method handles both.
        """
        if data is None:
            return default if default is not None else {}

        # If already a dict/list (from JSONB), return as is
        if isinstance(data, (dict, list)):
            return data

        if isinstance(data, str):
            if not data.strip():
                return default if default is not None else {}
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to deserialize JSON string: {e}")
                return default if default is not None else {}

        # Fallback
        return default if default is not None else {}

    def to_isoformat(self, dt: Optional[datetime]) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()

    def from_isoformat(self, iso_str: Optional[str]) -> Optional[datetime]:
        if not iso_str:
            return None
        try:
            return datetime.fromisoformat(iso_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse ISO format datetime: {e}")
            return None

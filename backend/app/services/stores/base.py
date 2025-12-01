"""
Base store class for Mindscape data persistence
Provides common database connection, transaction, and utility methods
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import Optional, Any
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class StoreError(Exception):
    """Base exception for store operations"""
    pass


class StoreNotFoundError(StoreError):
    """Resource not found"""
    pass


class StoreValidationError(StoreError):
    """Validation error"""
    pass


class StoreConstraintError(StoreError):
    """Database constraint violation"""
    pass


class StoreBase:
    """
    Base class for all domain stores

    Provides common functionality:
    - Database connection management
    - Transaction support
    - JSON serialization/deserialization
    - Time format conversion
    """

    def __init__(self, db_path: str):
        """
        Initialize store with database path

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    @contextmanager
    def get_connection(self):
        """
        Get database connection with proper cleanup

        Usage:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
                conn.commit()
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """
        Execute operations within a transaction

        Automatically commits on success, rolls back on error.

        Usage:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
                # No need to call conn.commit()
        """
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction rolled back: {e}")
                raise

    def serialize_json(self, data: Any) -> Optional[str]:
        """
        Serialize data to JSON string

        Args:
            data: Data to serialize (dict, list, etc.)

        Returns:
            JSON string or None if data is None
        """
        if data is None:
            return None
        try:
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize JSON: {e}")
            raise StoreValidationError(f"Invalid JSON data: {e}")

    def deserialize_json(self, data: Optional[str], default: Any = None) -> Any:
        """
        Deserialize JSON string to Python object

        Args:
            data: JSON string to deserialize (or sqlite3.Row object)
            default: Default value if data is None or empty

        Returns:
            Deserialized object or default value
        """
        # Handle None or empty data
        if data is None:
            return default if default is not None else {}

        # Handle sqlite3.Row objects by extracting the value
        # Check for sqlite3.Row by checking for the Row class name or by checking if it has keys() but not get()
        if hasattr(data, '__class__'):
            class_name = data.__class__.__name__
            module_name = getattr(data.__class__, '__module__', '')
            # Check if it's a sqlite3.Row (which has keys() but not get())
            is_row = (
                class_name == 'Row' or
                (hasattr(data, 'keys') and not hasattr(data, 'get')) or
                'sqlite3' in module_name
            )

            if is_row:
                # This is a sqlite3.Row object, try to extract the value
                logger.error(f"deserialize_json received sqlite3.Row object! This shouldn't happen. Type: {type(data)}, Module: {module_name}, Keys: {data.keys() if hasattr(data, 'keys') else 'N/A'}")
                # For JSON columns, sqlite3.Row should return the string value directly
                # But if it doesn't, we need to handle it
                try:
                    # Try to access as if it's a single column
                    if hasattr(data, 'keys') and len(data.keys()) == 1:
                        key = list(data.keys())[0]
                        data = data[key]
                    else:
                        # Multiple columns or can't access, convert to string
                        logger.warning(f"sqlite3.Row with multiple columns or access issue in deserialize_json: {data.keys() if hasattr(data, 'keys') else 'no keys'}")
                        data = str(data)
                except Exception as e:
                    logger.warning(f"Error extracting value from sqlite3.Row: {e}")
                    data = str(data) if data else None
                    if not data:
                        return default if default is not None else {}

        # If data is already a dict/list, return it
        if isinstance(data, (dict, list)):
            return data

        # Convert to string if not already
        if not isinstance(data, str):
            data = str(data)

        # Handle empty string
        if not data or data.strip() == '':
            return default if default is not None else {}

        try:
            # Try to parse as JSON string
            return json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to deserialize JSON, using default: {e}, data type: {type(data)}, data: {data[:100] if isinstance(data, str) else data}")
            return default if default is not None else {}

    def to_isoformat(self, dt: Optional[datetime]) -> Optional[str]:
        """
        Convert datetime to ISO format string

        Args:
            dt: Datetime object or None

        Returns:
            ISO format string or None
        """
        if dt is None:
            return None
        return dt.isoformat()

    def from_isoformat(self, iso_str: Optional[str]) -> Optional[datetime]:
        """
        Convert ISO format string to datetime

        Args:
            iso_str: ISO format string or None

        Returns:
            Datetime object or None
        """
        if not iso_str:
            return None
        try:
            return datetime.fromisoformat(iso_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse ISO format datetime: {e}")
            return None

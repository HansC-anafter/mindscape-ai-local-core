"""SQLAlchemy Base class for PostgreSQL models.

This Base is specifically for PostgreSQL models that require
PostgreSQL-specific types (UUID, JSONB, ARRAY, pgvector, etc.).

For SQLite models (workspace state), use StoreBase instead.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for PostgreSQL SQLAlchemy models.

    This Base is specifically for PostgreSQL models that require
    PostgreSQL-specific types (UUID, JSONB, ARRAY, pgvector, etc.).

    For SQLite models (workspace state), use StoreBase instead.

    Example:
        ```python
        from app.database import Base
        from sqlalchemy.dialects.postgresql import UUID, JSONB

        class MyModel(Base):
            __tablename__ = "my_table"
            id = Column(UUID(as_uuid=True), primary_key=True)
            data = Column(JSONB)
        ```
    """
    pass


"""Canonical facade for authoritative database migration order and configs."""

from __future__ import annotations

from pathlib import Path


AUTHORITATIVE_DATABASE_ORDER = ("postgres", "vector")


def authoritative_alembic_configs(backend_dir: Path) -> dict[str, Path]:
    """Return the only supported host migration configurations."""

    root = Path(backend_dir)
    return {
        "postgres": root / "alembic.postgres.ini",
        "vector": root / "alembic.vector.ini",
    }


__all__ = [
    "AUTHORITATIVE_DATABASE_ORDER",
    "authoritative_alembic_configs",
]

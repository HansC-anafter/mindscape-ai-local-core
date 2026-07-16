"""Facade for migration mutation admission and subprocess resource bounds."""

from __future__ import annotations

from pathlib import Path
from typing import MutableMapping

from backend.app.services.runtime_database_incident_gate import (
    require_runtime_database_mutation_allowed,
)


def require_migration_execution_allowed(
    alembic_config: Path,
    revision: str,
) -> None:
    require_runtime_database_mutation_allowed(
        f"alembic_upgrade:{alembic_config.name}:{revision}"
    )


def apply_migration_subprocess_policy(
    environment: MutableMapping[str, str],
) -> None:
    existing = environment.get("PGOPTIONS", "").strip()
    environment["PGOPTIONS"] = (
        existing + " -c lock_timeout=5000 -c statement_timeout=120000"
    ).strip()


__all__ = [
    "apply_migration_subprocess_policy",
    "require_migration_execution_allowed",
]

"""Transactional executor for one new independent Alembic branch revision."""

from __future__ import annotations

from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.database.engine_factory import create_session_semantics_engine


def execute_independent_revision(
    *,
    revision_script: Any,
    postgres_url: str,
    revision: str,
) -> bool:
    """Execute and record one independent revision without traversing other heads."""

    if str(getattr(revision_script, "revision", "")) != revision:
        raise ValueError("independent_revision_target_mismatch")
    if getattr(revision_script, "down_revision", None) is not None:
        raise ValueError("independent_revision_requires_base_parent")
    if not tuple(getattr(revision_script, "branch_labels", ()) or ()):
        raise ValueError("independent_revision_requires_branch_label")
    upgrade = getattr(getattr(revision_script, "module", None), "upgrade", None)
    if not callable(upgrade):
        raise ValueError("independent_revision_upgrade_missing")

    engine = create_session_semantics_engine(
        postgres_url,
        "local-core-independent-migration",
    )
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '120s'"))
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"alembic-independent:{revision}"},
            )
            already_applied = bool(
                connection.execute(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM alembic_version WHERE version_num = :revision"
                        ")"
                    ),
                    {"revision": revision},
                ).scalar()
            )
            if already_applied:
                return True

            migration_context = MigrationContext.configure(
                connection,
                opts={"transactional_ddl": True},
            )
            with Operations.context(migration_context):
                upgrade()
            connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) "
                    "SELECT :revision WHERE NOT EXISTS ("
                    "SELECT 1 FROM alembic_version WHERE version_num = :revision"
                    ")"
                ),
                {"revision": revision},
            )
            recorded = bool(
                connection.execute(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM alembic_version WHERE version_num = :revision"
                        ")"
                    ),
                    {"revision": revision},
                ).scalar()
            )
            if not recorded:
                raise RuntimeError("independent_revision_receipt_not_recorded")
        return True
    finally:
        engine.dispose()


__all__ = ["execute_independent_revision"]

"""Transactional executor for one direct child of an applied Alembic head."""

from __future__ import annotations

from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.database.engine_factory import create_session_semantics_engine


def execute_linear_revision(
    *,
    revision_script: Any,
    postgres_url: str,
    revision: str,
    expected_parent_revision: str,
) -> bool:
    """Apply one exact linear child without resolving unrelated DB heads."""
    if str(getattr(revision_script, "revision", "")) != revision:
        raise ValueError("linear_revision_target_mismatch")
    down_revision = getattr(revision_script, "down_revision", None)
    if not isinstance(down_revision, str) or down_revision != expected_parent_revision:
        raise ValueError("linear_revision_parent_mismatch")
    upgrade = getattr(getattr(revision_script, "module", None), "upgrade", None)
    if not callable(upgrade):
        raise ValueError("linear_revision_upgrade_missing")

    engine = create_session_semantics_engine(
        postgres_url,
        "local-core-linear-migration",
    )
    connection = engine.connect()
    lock_key = f"alembic-linear:{expected_parent_revision}:{revision}"
    lock_acquired = False
    try:
        connection.execute(
            text("SELECT pg_advisory_lock(hashtext(:lock_key))"),
            {"lock_key": lock_key},
        )
        connection.commit()
        lock_acquired = True
        connection.execute(text("SET SESSION lock_timeout = '5s'"))
        connection.execute(text("SET SESSION statement_timeout = '120s'"))
        connection.commit()

        with connection.begin():
            current_revisions = {
                str(row[0])
                for row in connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).fetchall()
            }
            if revision in current_revisions:
                return True
            if expected_parent_revision not in current_revisions:
                raise RuntimeError("linear_revision_parent_head_changed")

        migration_context = MigrationContext.configure(
            connection,
            opts={"transactional_ddl": True},
        )
        with migration_context.begin_transaction():
            with Operations.context(migration_context):
                upgrade()

        with connection.begin():
            connection.execute(
                text("LOCK TABLE alembic_version IN SHARE ROW EXCLUSIVE MODE")
            )
            current_revisions = {
                str(row[0])
                for row in connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).fetchall()
            }
            if revision in current_revisions:
                return True
            if expected_parent_revision not in current_revisions:
                raise RuntimeError("linear_revision_parent_head_changed")

            result = connection.execute(
                text(
                    "UPDATE alembic_version "
                    "SET version_num = :revision "
                    "WHERE version_num = :parent_revision"
                ),
                {
                    "revision": revision,
                    "parent_revision": expected_parent_revision,
                },
            )
            if result.rowcount != 1:
                raise RuntimeError("linear_revision_head_compare_and_swap_failed")

            readback = {
                str(row[0])
                for row in connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).fetchall()
            }
            if revision not in readback or expected_parent_revision in readback:
                raise RuntimeError("linear_revision_receipt_readback_mismatch")
        return True
    finally:
        if connection.in_transaction():
            connection.rollback()
        if lock_acquired:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )
            connection.commit()
        connection.close()
        engine.dispose()


__all__ = ["execute_linear_revision"]

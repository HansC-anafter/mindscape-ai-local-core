"""Normalize redundant Alembic heads without changing schema coverage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Sequence

from sqlalchemy import text

from app.database.engine_factory import create_session_semantics_engine


PlanStatus = Literal["clean", "ready", "blocked_unresolved"]


@dataclass(frozen=True)
class MigrationHeadNormalizationPlan:
    status: PlanStatus
    current_revisions: tuple[str, ...]
    redundant_revisions: tuple[str, ...]
    retained_revisions: tuple[str, ...]
    unresolved_revisions: tuple[str, ...]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def plan_redundant_heads(
    *,
    script_directory: Any,
    current_revisions: Sequence[str],
) -> MigrationHeadNormalizationPlan:
    """Prove which current rows are ancestors of another current row."""

    current = tuple(sorted(set(str(item) for item in current_revisions)))
    ancestry: dict[str, set[str]] = {}
    unresolved: list[str] = []
    for descendant in current:
        try:
            ancestry[descendant] = {
                str(revision.revision)
                for revision in script_directory.iterate_revisions(
                    descendant,
                    "base",
                )
                if getattr(revision, "revision", None)
            }
        except Exception:
            unresolved.append(descendant)

    if unresolved:
        return MigrationHeadNormalizationPlan(
            status="blocked_unresolved",
            current_revisions=current,
            redundant_revisions=(),
            retained_revisions=current,
            unresolved_revisions=tuple(sorted(unresolved)),
        )

    redundant = {
        ancestor
        for descendant, ancestors in ancestry.items()
        for ancestor in current
        if ancestor != descendant and ancestor in ancestors
    }
    retained = tuple(
        revision for revision in current if revision not in redundant
    )
    return MigrationHeadNormalizationPlan(
        status="ready" if redundant else "clean",
        current_revisions=current,
        redundant_revisions=tuple(sorted(redundant)),
        retained_revisions=retained,
        unresolved_revisions=(),
    )


class MigrationHeadNormalizationFacade:
    """One explicit, compare-and-swap writer for redundant head rows."""

    def __init__(self, *, script_directory: Any, postgres_url: str):
        self.script_directory = script_directory
        self.postgres_url = postgres_url

    def plan(
        self,
        current_revisions: Sequence[str],
    ) -> MigrationHeadNormalizationPlan:
        return plan_redundant_heads(
            script_directory=self.script_directory,
            current_revisions=current_revisions,
        )

    def apply(
        self,
        expected_plan: MigrationHeadNormalizationPlan,
    ) -> MigrationHeadNormalizationPlan:
        if expected_plan.status != "ready":
            raise ValueError("migration_head_normalization_plan_not_ready")

        engine = create_session_semantics_engine(
            self.postgres_url,
            "local-core-migration-head-normalization",
        )
        try:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(
                    text("SET LOCAL statement_timeout = '30s'")
                )
                connection.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "hashtext('alembic-head-normalization'))"
                    )
                )
                connection.execute(
                    text(
                        "LOCK TABLE alembic_version "
                        "IN SHARE ROW EXCLUSIVE MODE"
                    )
                )
                locked_current = tuple(
                    str(row[0])
                    for row in connection.execute(
                        text(
                            "SELECT version_num FROM alembic_version "
                            "ORDER BY version_num"
                        )
                    ).fetchall()
                )
                locked_plan = self.plan(locked_current)
                if locked_plan != expected_plan:
                    raise RuntimeError(
                        "migration_head_set_changed_during_normalization"
                    )

                result = connection.execute(
                    text(
                        "DELETE FROM alembic_version "
                        "WHERE version_num = ANY("
                        "CAST(:revisions AS varchar[]))"
                    ),
                    {
                        "revisions": list(
                            expected_plan.redundant_revisions
                        )
                    },
                )
                if result.rowcount != len(
                    expected_plan.redundant_revisions
                ):
                    raise RuntimeError(
                        "migration_head_normalization_delete_mismatch"
                    )
                readback = tuple(
                    str(row[0])
                    for row in connection.execute(
                        text(
                            "SELECT version_num FROM alembic_version "
                            "ORDER BY version_num"
                        )
                    ).fetchall()
                )
                if readback != expected_plan.retained_revisions:
                    raise RuntimeError(
                        "migration_head_normalization_readback_mismatch"
                    )
        finally:
            engine.dispose()

        return MigrationHeadNormalizationPlan(
            status="clean",
            current_revisions=expected_plan.retained_revisions,
            redundant_revisions=(),
            retained_revisions=expected_plan.retained_revisions,
            unresolved_revisions=(),
        )


__all__ = [
    "MigrationHeadNormalizationFacade",
    "MigrationHeadNormalizationPlan",
    "plan_redundant_heads",
]

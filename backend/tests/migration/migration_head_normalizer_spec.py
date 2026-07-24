from pathlib import Path

from backend.app.services.migrations.head_normalizer import (
    plan_redundant_heads,
)


class _Revision:
    def __init__(self, revision: str):
        self.revision = revision


class _ScriptDirectory:
    def __init__(
        self,
        chains: dict[str, list[str]],
        *,
        unresolved: set[str] | None = None,
    ):
        self.chains = chains
        self.unresolved = unresolved or set()

    def iterate_revisions(self, head: str, _base: str):
        if head in self.unresolved:
            raise LookupError(head)
        return [_Revision(item) for item in self.chains[head]]


def test_plan_removes_only_ancestors_of_retained_current_heads() -> None:
    script = _ScriptDirectory(
        {
            "root": ["root"],
            "middle": ["middle", "root"],
            "latest": ["latest", "middle", "root"],
            "independent": ["independent"],
        }
    )

    plan = plan_redundant_heads(
        script_directory=script,
        current_revisions=[
            "root",
            "middle",
            "latest",
            "independent",
        ],
    )

    assert plan.status == "ready"
    assert plan.redundant_revisions == ("middle", "root")
    assert plan.retained_revisions == ("independent", "latest")
    assert plan.unresolved_revisions == ()


def test_plan_fails_closed_when_any_current_revision_is_unresolved() -> None:
    script = _ScriptDirectory(
        {
            "latest": ["latest"],
        },
        unresolved={"unknown"},
    )

    plan = plan_redundant_heads(
        script_directory=script,
        current_revisions=["latest", "unknown"],
    )

    assert plan.status == "blocked_unresolved"
    assert plan.redundant_revisions == ()
    assert plan.retained_revisions == ("latest", "unknown")
    assert plan.unresolved_revisions == ("unknown",)


def test_apply_path_locks_compares_and_parameterizes_delete() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (
        root / "backend/app/services/migrations/head_normalizer.py"
    ).read_text(encoding="utf-8")

    assert "pg_advisory_xact_lock" in source
    assert "LOCK TABLE alembic_version" in source
    assert "IN SHARE ROW EXCLUSIVE MODE" in source
    assert "locked_plan != expected_plan" in source
    assert "CAST(:revisions AS varchar[])" in source
    assert "DELETE FROM alembic_version" in source

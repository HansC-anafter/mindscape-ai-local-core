from pathlib import Path


def test_gitignore_uses_neutral_capability_quarantine_path():
    repo_root = Path(__file__).resolve().parents[2]
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")

    assert (
        "backend/alembic_migrations/postgres/capability-installed-legacy/"
        in gitignore
    )


def test_gitignore_does_not_hardcode_pack_domains():
    repo_root = Path(__file__).resolve().parents[2]
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")

    forbidden_terms = {
        "antigravity",
        "yogacoach",
        "sonic_space",
        "ig_",
        "grid_posts",
        "course_production",
        "motion_segments",
        "mesh_assets",
    }
    found_terms = sorted(term for term in forbidden_terms if term in gitignore)

    assert found_terms == []

from pathlib import Path


REQUIRED_MARKER = "<!-- AUTHORIZATION-PRESERVING-CHANGE-CONTROL: REQUIRED -->"


def test_every_repo_skill_carries_authorization_preserving_gate() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    skills_root = repo_root / ".agent" / "skills"
    skill_files = {
        skill_file.resolve()
        for skill_file in skills_root.glob("*/SKILL.md")
        if skill_file.is_file()
    }

    assert skill_files, "No repository skills were discovered"

    invalid = [
        str(skill_file.relative_to(repo_root))
        for skill_file in sorted(skill_files)
        if skill_file.read_text(encoding="utf-8").count(REQUIRED_MARKER) != 1
    ]
    assert not invalid, (
        "Every repository skill must carry exactly one authorization-preserving "
        f"change control gate; invalid: {invalid}"
    )

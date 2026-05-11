from pathlib import Path


PR_TEMPLATE = Path(
    Path(__file__).resolve().parents[3] / ".github/pull_request_template.md"
)


def test_pr_template_includes_modular_entry_checklist() -> None:
    content = PR_TEMPLATE.read_text(encoding="utf-8")

    assert "## Modular Entry Check" in content
    assert "This change opens or confirms a modular entrypoint" in content
    assert "Legacy entrypoint is reduced to a thin wrapper where applicable" in content
    assert "Leaf-only exception claimed" in content
    assert "Changed files:" in content
    assert "Why leaf-only:" in content
    assert "Why no new boundary:" in content
    assert "Why future refactor cost does not increase:" in content

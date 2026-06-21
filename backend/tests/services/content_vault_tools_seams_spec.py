from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.tools.content_vault import (
    ContentVaultBuildPromptTool,
    ContentVaultLoadContextTool,
    ContentVaultWritePostsTool,
)
from backend.app.services.tools.content_vault.vault_tools import (
    ContentVaultMergeContextTool,
    parse_frontmatter,
)
from backend.app.services.tools.registry_core.builtin import register_content_vault_tools


def write_markdown(path: Path, frontmatter: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8")


def test_parse_frontmatter_returns_metadata_and_body():
    frontmatter, body = parse_frontmatter("---\ntitle: Hello\n---\nBody text")

    assert frontmatter == {"title": "Hello"}
    assert body == "Body text"


def test_parse_frontmatter_fails_closed_on_invalid_yaml():
    content = "---\ninvalid: [\n---\nBody text"

    frontmatter, body = parse_frontmatter(content)

    assert frontmatter == {}
    assert body == content


@pytest.mark.asyncio
async def test_load_context_reads_series_arc_and_recent_posts(tmp_path):
    write_markdown(
        tmp_path / "series" / "mindful-coffee.md",
        "theme: Coffee\nseries_id: mindful-coffee",
        "Series body",
    )
    write_markdown(
        tmp_path / "arcs" / "arc-1.md",
        "arc_theme: Morning\narc_id: arc-1",
        "Arc body",
    )
    write_markdown(
        tmp_path / "posts" / "instagram" / "new.md",
        "series_id: mindful-coffee\nstatus: published\ndate: '2026-06-21'\nsequence: 2\nnarrative_phase: open\nemotion: calm",
        "New post",
    )
    write_markdown(
        tmp_path / "posts" / "instagram" / "draft.md",
        "series_id: mindful-coffee\nstatus: draft\ndate: '2026-06-22'\nsequence: 3",
        "Draft post",
    )
    write_markdown(
        tmp_path / "posts" / "instagram" / "other.md",
        "series_id: other\nstatus: published\ndate: '2026-06-23'\nsequence: 4",
        "Other post",
    )
    tool = ContentVaultLoadContextTool(str(tmp_path))

    context = await tool.execute("mindful-coffee", "arc-1", n_recent_posts=5)

    assert context["series"]["body"] == "Series body"
    assert context["arc"]["frontmatter"]["arc_theme"] == "Morning"
    assert [post["text"] for post in context["recent_posts"]] == ["New post"]


@pytest.mark.asyncio
async def test_write_posts_creates_draft_with_next_sequence(tmp_path):
    write_markdown(
        tmp_path / "posts" / "instagram" / "2026-06-20-mindful-coffee-existing.md",
        "series_id: mindful-coffee\nsequence: 7",
        "Existing post",
    )
    tool = ContentVaultWritePostsTool(str(tmp_path))

    result = await tool.execute(
        "mindful-coffee",
        "arc-1",
        [
            {
                "text": "Fresh idea",
                "hashtags": ["coffee", "mindful"],
                "narrative_phase": "middle",
                "emotion": "warm",
                "reasoning": "Fits the arc",
            }
        ],
    )

    written_path = Path(result["files"][0])
    frontmatter, body = parse_frontmatter(written_path.read_text(encoding="utf-8"))
    assert written_path.parent == tmp_path / "posts" / "instagram"
    assert frontmatter["sequence"] == 8
    assert frontmatter["status"] == "draft"
    assert frontmatter["hashtags_count"] == 2
    assert "Fresh idea" in body
    assert "#coffee #mindful" in body


def test_public_exports_and_registry_registration_share_facade(tmp_path):
    tools = register_content_vault_tools(str(tmp_path))

    assert [tool.metadata.name for tool in tools] == [
        "content_vault.load_context",
        "content_vault.build_prompt",
        "content_vault.write_posts",
        "content_vault.merge_context",
    ]
    assert isinstance(tools[0], ContentVaultLoadContextTool)
    assert isinstance(tools[1], ContentVaultBuildPromptTool)
    assert isinstance(tools[2], ContentVaultWritePostsTool)
    assert isinstance(tools[3], ContentVaultMergeContextTool)

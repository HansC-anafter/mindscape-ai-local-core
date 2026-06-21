"""Write-side content vault tools."""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.content_vault.vault_tools_core.frontmatter import (
    parse_frontmatter,
)
from backend.app.services.tools.schemas import ToolInputSchema, ToolMetadata

logger = logging.getLogger(__name__)


class ContentVaultWritePostsTool(MindscapeTool):
    """Write generated posts back to content vault."""

    def __init__(self, vault_path: Optional[str] = None):
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH") or str(
                Path.home() / "content-vault"
            )
        self.base_vault_path = Path(vault_path).expanduser().resolve()

        if not self.base_vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        metadata = ToolMetadata(
            name="content_vault.write_posts",
            description="Write generated posts to content vault",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "series_id": {
                        "type": "string",
                        "description": "Series ID",
                    },
                    "arc_id": {
                        "type": "string",
                        "description": "Arc ID",
                    },
                    "posts": {
                        "type": "array",
                        "description": "List of generated posts",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "hashtags": {"type": "array", "items": {"type": "string"}},
                                "narrative_phase": {"type": "string"},
                                "emotion": {"type": "string"},
                                "reasoning": {"type": "string"},
                            },
                        },
                    },
                    "platform": {
                        "type": "string",
                        "description": "Platform (instagram, facebook, etc.)",
                        "default": "instagram",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID (optional, for workspace-specific vault)",
                    },
                },
                required=["series_id", "arc_id", "posts"],
            ),
            category="data",
            source_type="builtin",
            provider="content_vault",
            danger_level="low",
        )
        super().__init__(metadata)

    def _get_vault_path(self, workspace_id: Optional[str] = None) -> Path:
        """Get vault path for workspace."""
        if workspace_id:
            vault_path = self.base_vault_path / workspace_id
            if not vault_path.exists():
                vault_path.mkdir(parents=True, exist_ok=True)
            return vault_path
        return self.base_vault_path

    async def execute(
        self,
        series_id: str,
        arc_id: str,
        posts: List[Dict],
        platform: str = "instagram",
        workspace_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, List[str]]:
        """Write posts back to vault."""
        vault_path = self._get_vault_path(workspace_id)
        written_files = []

        for i, post in enumerate(posts, 1):
            date_str = datetime.now().strftime("%Y-%m-%d")
            sequence = self._get_next_sequence(series_id, platform, vault_path)
            filename = f"{date_str}-{series_id}-{sequence:03d}-draft{i}.md"

            frontmatter = {
                "doc_type": "post",
                "post_id": f"{series_id}-{sequence:03d}",
                "series_id": series_id,
                "arc_id": arc_id,
                "platform": platform,
                "post_type": "single_image",
                "sequence": sequence,
                "date": date_str,
                "status": "draft",
                "word_count": len(post.get("text", "")),
                "hashtags_count": len(post.get("hashtags", [])),
                "narrative_phase": post.get("narrative_phase", "unknown"),
                "emotion": post.get("emotion", "neutral"),
            }

            full_content = self._build_document(frontmatter, post)
            output_path = vault_path / "posts" / platform / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(full_content)

            written_files.append(str(output_path))

        return {"files": written_files}

    def _get_next_sequence(
        self,
        series_id: str,
        platform: str,
        vault_path: Optional[Path] = None,
    ) -> int:
        """Get next sequence number."""
        if vault_path is None:
            vault_path = self.base_vault_path
        posts_dir = vault_path / "posts" / platform

        if not posts_dir.exists():
            return 1

        max_seq = 0
        for md_file in posts_dir.glob(f"*{series_id}*.md"):
            try:
                frontmatter, _ = parse_frontmatter(md_file.read_text(encoding="utf-8"))
                seq = frontmatter.get("sequence", 0)
                max_seq = max(max_seq, seq)
            except Exception as e:
                logger.warning(f"Failed to parse sequence from {md_file}: {e}")
                continue

        return max_seq + 1

    def _build_document(self, frontmatter: Dict, post: Dict) -> str:
        """Build complete Markdown document."""
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)
        hashtags = post.get("hashtags", [])
        hashtags_str = " ".join(["#" + tag for tag in hashtags]) if hashtags else ""
        post_text = post.get("text", "")

        return f"""---
{fm_yaml}---

# Post Content

{post_text}

{hashtags_str}

---

## Creation Notes

**Generated At**: {datetime.now().isoformat()}
**AI Reasoning**: {post.get('reasoning', 'N/A')}
"""

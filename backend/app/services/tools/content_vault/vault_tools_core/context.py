"""Read-side context loading for content vault tools."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.content_vault.vault_tools_core.frontmatter import (
    parse_frontmatter,
)
from backend.app.services.tools.schemas import ToolInputSchema, ToolMetadata

logger = logging.getLogger(__name__)


class ContentVaultLoadContextTool(MindscapeTool):
    """Load narrative context from Series, Arc, and recent Posts."""

    def __init__(self, vault_path: Optional[str] = None):
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH") or str(
                Path.home() / "content-vault"
            )
        self.base_vault_path = Path(vault_path).expanduser().resolve()

        if not self.base_vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        metadata = ToolMetadata(
            name="content_vault.load_context",
            description="Load narrative context from content vault",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "series_id": {
                        "type": "string",
                        "description": "Series ID (e.g., 'mindful-coffee')",
                    },
                    "arc_id": {
                        "type": "string",
                        "description": "Arc ID (e.g., '2025w52-new-year')",
                    },
                    "n_recent_posts": {
                        "type": "integer",
                        "description": "Number of recent posts to load",
                        "default": 20,
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID (optional, for workspace-specific vault)",
                    },
                },
                required=["series_id", "arc_id"],
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
        n_recent_posts: int = 20,
        workspace_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Load narrative context."""
        vault_path = self._get_vault_path(workspace_id)
        context = {}

        series_path = vault_path / "series" / f"{series_id}.md"
        if not series_path.exists():
            raise FileNotFoundError(f"Series not found: {series_id}")
        series_doc = self._parse_markdown(series_path)
        context["series"] = series_doc

        arc_path = vault_path / "arcs" / f"{arc_id}.md"
        if not arc_path.exists():
            raise FileNotFoundError(f"Arc not found: {arc_id}")
        arc_doc = self._parse_markdown(arc_path)
        context["arc"] = arc_doc

        posts_dir = vault_path / "posts" / "instagram"
        recent_posts = self._load_recent_posts(
            posts_dir,
            series_id,
            n_recent_posts,
        )
        context["recent_posts"] = recent_posts

        return context

    def _parse_markdown(self, file_path: Path) -> Dict[str, Any]:
        """Parse Markdown and YAML frontmatter."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)

        return {
            "frontmatter": frontmatter,
            "body": body.strip(),
            "file_path": str(file_path),
        }

    def _load_recent_posts(
        self,
        posts_dir: Path,
        series_id: str,
        n: int,
    ) -> List[Dict[str, Any]]:
        """Load recent published posts for a series."""
        if not posts_dir.exists():
            logger.warning(f"Posts directory does not exist: {posts_dir}")
            return []

        all_posts = []

        for md_file in posts_dir.glob("*.md"):
            try:
                doc = self._parse_markdown(md_file)
                fm = doc["frontmatter"]

                if fm.get("series_id") == series_id and fm.get("status") == "published":
                    all_posts.append(
                        {
                            "sequence": fm.get("sequence", 0),
                            "date": fm.get("date", ""),
                            "text": doc["body"],
                            "narrative_phase": fm.get("narrative_phase", "unknown"),
                            "emotion": fm.get("emotion", "neutral"),
                            "frontmatter": fm,
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to parse post {md_file}: {e}")
                continue

        all_posts.sort(key=lambda p: p["date"], reverse=True)
        return all_posts[:n]

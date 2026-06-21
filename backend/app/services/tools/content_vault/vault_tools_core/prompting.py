"""Prompt construction and context merging for content vault tools."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolInputSchema, ToolMetadata


class ContentVaultBuildPromptTool(MindscapeTool):
    """Build generation prompt from context."""

    def __init__(self):
        metadata = ToolMetadata(
            name="content_vault.build_prompt",
            description="Build LLM prompt from narrative context",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "series_context": {
                        "type": "object",
                        "description": "Series context from load_context",
                    },
                    "arc_context": {
                        "type": "object",
                        "description": "Arc context from load_context",
                    },
                    "recent_posts": {
                        "type": "array",
                        "description": "Recent posts from load_context",
                    },
                    "user_input": {
                        "type": "string",
                        "description": "User input or topic",
                        "default": "",
                    },
                },
                required=["series_context", "arc_context", "recent_posts"],
            ),
            category="data",
            source_type="builtin",
            provider="content_vault",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        series_context: Dict,
        arc_context: Dict,
        recent_posts: List[Dict],
        user_input: str = "",
    ) -> Dict[str, str]:
        """Build complete prompt."""
        series_fm = series_context.get("frontmatter", {})
        arc_fm = arc_context.get("frontmatter", {})
        recent_posts_text = self._format_posts(recent_posts[:10])

        prompt = f"""# Task: Generate new Instagram posts

## Series Contract

**Theme**: {series_fm.get('theme', 'N/A')}
**Tone**: {series_fm.get('tone', 'N/A')}
**Target Audience**: {series_fm.get('target_audience', 'N/A')}

Style Guide:
{yaml.dump(series_fm.get('style_guide', {}), allow_unicode=True, default_flow_style=False)}

## Current Narrative Arc

**Arc Theme**: {arc_fm.get('arc_theme', 'N/A')}
**Emotional Arc**: {yaml.dump(arc_fm.get('emotional_arc', []), allow_unicode=True, default_flow_style=False)}
**Key Messages**: {arc_fm.get('key_messages', [])}

Narrative Structure:
{yaml.dump(arc_fm.get('narrative_structure', []), allow_unicode=True, default_flow_style=False)}

## Recent 10 Posts (for reference)

{recent_posts_text}

## User Input

{user_input if user_input else "(No specific topic, generate based on arc planning)"}

## Generation Requirements

1. **Continue Narrative**: Naturally connect with recent posts' emotions and themes
2. **Match Arc**: Echo current arc's key messages
3. **Maintain Style**: Follow series contract's tone
4. **Avoid Repetition**: Don't use similar expressions
5. **Generate 3 Versions**: Provide different angles

Please generate 3 versions of posts.
"""

        return {"prompt": prompt}

    def _format_posts(self, posts: List[Dict]) -> str:
        """Format posts list."""
        if not posts:
            return "No recent posts found."

        lines = []
        for i, post in enumerate(posts, 1):
            text_preview = post.get("text", "")[:150]
            lines.append(
                f"{i}. [{post.get('date', 'N/A')}] "
                f"({post.get('narrative_phase', 'unknown')})\n"
                f"   {text_preview}...\n"
            )
        return "\n".join(lines)


class ContentVaultMergeContextTool(MindscapeTool):
    """Merge file system context with vector search context."""

    def __init__(self, vault_path: Optional[str] = None):
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH") or str(
                Path.home() / "content-vault"
            )
        self.vault_path = Path(vault_path).expanduser().resolve()

        metadata = ToolMetadata(
            name="content_vault.merge_context",
            description="Merge file system context with vector search context",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "file_context": {
                        "type": "object",
                        "description": "Context from file system",
                    },
                    "vector_context": {
                        "type": "array",
                        "description": "Context from vector search",
                    },
                },
                required=[],
            ),
            category="data",
            source_type="builtin",
            provider="content_vault",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        file_context: Optional[Dict[str, Any]] = None,
        vector_context: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Merge file system context with vector search context."""
        merged = {
            "file_context": file_context or {},
            "vector_context": vector_context or [],
            "merged_prompt": "",
        }

        parts = []

        if file_context:
            if file_context.get("series"):
                parts.append(
                    f"## Series Context:\n{file_context['series'].get('content', '')}"
                )
            if file_context.get("arc"):
                parts.append(f"## Arc Context:\n{file_context['arc'].get('content', '')}")
            if file_context.get("recent_posts"):
                parts.append("## Recent Posts:")
                for post in file_context["recent_posts"][:10]:
                    parts.append(f"- {post.get('text', '')[:200]}...")

        if vector_context:
            parts.append("\n## Related Content (Semantic Search):")
            for i, doc in enumerate(vector_context[:5], 1):
                similarity = doc.get("similarity", 0)
                content = doc.get("content", "")
                parts.append(
                    f"\n### Match {i} (similarity: {similarity:.2f}):\n"
                    f"{content[:300]}..."
                )

        merged["merged_prompt"] = "\n\n".join(parts)
        return merged

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata for legacy callers."""
        return self.metadata

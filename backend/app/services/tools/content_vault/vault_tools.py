"""
Content Vault Tools

File-system based content vault tools (tool-agnostic).
Supports Series, Arc, and Post document types with YAML frontmatter.
"""

import yaml
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


def parse_frontmatter(content: str) -> tuple:
    """
    Parse YAML frontmatter from markdown content

    Returns:
        (frontmatter_dict, body_content)
    """
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if match:
        frontmatter_str = match.group(1)
        body = match.group(2)
        try:
            frontmatter = yaml.safe_load(frontmatter_str) or {}
            return frontmatter, body
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse frontmatter YAML: {e}")
            return {}, content
    else:
        return {}, content


class ContentVaultLoadContextTool(MindscapeTool):
    """Load narrative context (Series + Arc + Recent Posts)"""

    def __init__(self, vault_path: Optional[str] = None):
        import os
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH") or str(Path.home() / "content-vault")
        self.vault_path = Path(vault_path).expanduser().resolve()

        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        metadata = ToolMetadata(
            name="content_vault.load_context",
            description="Load narrative context from content vault",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "series_id": {
                        "type": "string",
                        "description": "Series ID (e.g., 'mindful-coffee')"
                    },
                    "arc_id": {
                        "type": "string",
                        "description": "Arc ID (e.g., '2025w52-new-year')"
                    },
                    "n_recent_posts": {
                        "type": "integer",
                        "description": "Number of recent posts to load",
                        "default": 20
                    },
                },
                required=["series_id", "arc_id"]
            ),
            category="data",
            source_type="builtin",
            provider="content_vault",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        series_id: str,
        arc_id: str,
        n_recent_posts: int = 20
    ) -> Dict[str, Any]:
        """Load narrative context"""

        context = {}

        # 1. Load Series
        series_path = self.vault_path / "series" / f"{series_id}.md"
        if not series_path.exists():
            raise FileNotFoundError(f"Series not found: {series_id}")
        series_doc = self._parse_markdown(series_path)
        context['series'] = series_doc

        # 2. Load Arc
        arc_path = self.vault_path / "arcs" / f"{arc_id}.md"
        if not arc_path.exists():
            raise FileNotFoundError(f"Arc not found: {arc_id}")
        arc_doc = self._parse_markdown(arc_path)
        context['arc'] = arc_doc

        # 3. Load recent Posts
        posts_dir = self.vault_path / "posts" / "instagram"
        recent_posts = self._load_recent_posts(
            posts_dir,
            series_id,
            n_recent_posts
        )
        context['recent_posts'] = recent_posts

        return context

    def _parse_markdown(self, file_path: Path) -> Dict[str, Any]:
        """Parse Markdown + YAML frontmatter"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)

        return {
            'frontmatter': frontmatter,
            'body': body.strip(),
            'file_path': str(file_path),
        }

    def _load_recent_posts(
        self,
        posts_dir: Path,
        series_id: str,
        n: int
    ) -> List[Dict[str, Any]]:
        """Load recent N Posts"""
        if not posts_dir.exists():
            logger.warning(f"Posts directory does not exist: {posts_dir}")
            return []

        all_posts = []

        for md_file in posts_dir.glob("*.md"):
            try:
                doc = self._parse_markdown(md_file)
                fm = doc['frontmatter']

                # Filter: same series + published
                if (fm.get('series_id') == series_id and
                    fm.get('status') == 'published'):
                    all_posts.append({
                        'sequence': fm.get('sequence', 0),
                        'date': fm.get('date', ''),
                        'text': doc['body'],
                        'narrative_phase': fm.get('narrative_phase', 'unknown'),
                        'emotion': fm.get('emotion', 'neutral'),
                        'frontmatter': fm,
                    })
            except Exception as e:
                logger.warning(f"Failed to parse post {md_file}: {e}")
                continue

        # Sort and take top N
        all_posts.sort(key=lambda p: p['date'], reverse=True)
        return all_posts[:n]


class ContentVaultBuildPromptTool(MindscapeTool):
    """Build generation prompt from context"""

    def __init__(self):
        metadata = ToolMetadata(
            name="content_vault.build_prompt",
            description="Build LLM prompt from narrative context",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "series_context": {
                        "type": "object",
                        "description": "Series context from load_context"
                    },
                    "arc_context": {
                        "type": "object",
                        "description": "Arc context from load_context"
                    },
                    "recent_posts": {
                        "type": "array",
                        "description": "Recent posts from load_context"
                    },
                    "user_input": {
                        "type": "string",
                        "description": "User input or topic",
                        "default": ""
                    },
                },
                required=["series_context", "arc_context", "recent_posts"]
            ),
            category="data",
            source_type="builtin",
            provider="content_vault",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        series_context: Dict,
        arc_context: Dict,
        recent_posts: List[Dict],
        user_input: str = ""
    ) -> Dict[str, str]:
        """Build complete prompt"""

        # Extract key information
        series_fm = series_context.get('frontmatter', {})
        arc_fm = arc_context.get('frontmatter', {})

        # Format recent posts
        recent_posts_text = self._format_posts(recent_posts[:10])

        # Build prompt
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
        """Format posts list"""
        if not posts:
            return "No recent posts found."

        lines = []
        for i, post in enumerate(posts, 1):
            text_preview = post.get('text', '')[:150]
            lines.append(
                f"{i}. [{post.get('date', 'N/A')}] ({post.get('narrative_phase', 'unknown')})\n"
                f"   {text_preview}...\n"
            )
        return "\n".join(lines)


class ContentVaultWritePostsTool(MindscapeTool):
    """Write generated posts back to content vault"""

    def __init__(self, vault_path: Optional[str] = None):
        import os
        if vault_path is None:
            vault_path = os.getenv("CONTENT_VAULT_PATH") or str(Path.home() / "content-vault")
        self.vault_path = Path(vault_path).expanduser().resolve()

        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        metadata = ToolMetadata(
            name="content_vault.write_posts",
            description="Write generated posts to content vault",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "series_id": {
                        "type": "string",
                        "description": "Series ID"
                    },
                    "arc_id": {
                        "type": "string",
                        "description": "Arc ID"
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
                                "reasoning": {"type": "string"}
                            }
                        }
                    },
                    "platform": {
                        "type": "string",
                        "description": "Platform (instagram, facebook, etc.)",
                        "default": "instagram"
                    },
                },
                required=["series_id", "arc_id", "posts"]
            ),
            category="data",
            source_type="builtin",
            provider="content_vault",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        series_id: str,
        arc_id: str,
        posts: List[Dict],
        platform: str = "instagram"
    ) -> Dict[str, List[str]]:
        """Write posts back to vault"""

        written_files = []

        for i, post in enumerate(posts, 1):
            # Generate filename
            date_str = datetime.now().strftime("%Y-%m-%d")
            sequence = self._get_next_sequence(series_id, platform)
            filename = f"{date_str}-{series_id}-{sequence:03d}-draft{i}.md"

            # Build frontmatter
            frontmatter = {
                'doc_type': 'post',
                'post_id': f"{series_id}-{sequence:03d}",
                'series_id': series_id,
                'arc_id': arc_id,
                'platform': platform,
                'post_type': 'single_image',
                'sequence': sequence,
                'date': date_str,
                'status': 'draft',
                'word_count': len(post.get('text', '')),
                'hashtags_count': len(post.get('hashtags', [])),
                'narrative_phase': post.get('narrative_phase', 'unknown'),
                'emotion': post.get('emotion', 'neutral'),
            }

            # Build complete document
            full_content = self._build_document(frontmatter, post)

            # Write file
            output_path = self.vault_path / "posts" / platform / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_content)

            written_files.append(str(output_path))

        return {"files": written_files}

    def _get_next_sequence(self, series_id: str, platform: str) -> int:
        """Get next sequence number"""
        posts_dir = self.vault_path / "posts" / platform

        if not posts_dir.exists():
            return 1

        max_seq = 0
        for md_file in posts_dir.glob(f"*{series_id}*.md"):
            try:
                frontmatter, _ = parse_frontmatter(md_file.read_text(encoding='utf-8'))
                seq = frontmatter.get('sequence', 0)
                max_seq = max(max_seq, seq)
            except Exception as e:
                logger.warning(f"Failed to parse sequence from {md_file}: {e}")
                continue

        return max_seq + 1

    def _build_document(self, frontmatter: Dict, post: Dict) -> str:
        """Build complete Markdown document"""
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)
        hashtags = post.get('hashtags', [])
        hashtags_str = ' '.join(['#' + tag for tag in hashtags]) if hashtags else ''

        # Extract post text (remove hashtags if already in text)
        post_text = post.get('text', '')

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


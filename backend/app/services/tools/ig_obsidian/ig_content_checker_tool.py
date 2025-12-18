"""
IG Content Checker Tool

Tool for checking IG Post content for compliance issues including medical/investment
claims, copyright, personal data, and brand tone.
"""
import logging
from typing import Dict, Any, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolExecutionResult,
    ToolDangerLevel,
    ToolSourceType,
    ToolInputSchema,
    ToolCategory
)
from backend.app.services.ig_obsidian.content_checker import ContentChecker

logger = logging.getLogger(__name__)


class IGContentCheckerTool(MindscapeTool):
    """Tool for checking IG Post content for compliance issues"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "content": {
                    "type": "string",
                    "description": "Post content text to check"
                },
                "frontmatter": {
                    "type": "object",
                    "description": "Post frontmatter (optional)"
                },
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault (optional, for reading from file)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Path to post Markdown file (relative to vault, optional)"
                }
            },
            required=[]
        )

        metadata = ToolMetadata(
            name="ig_content_checker_tool",
            description="Check IG Post content for compliance issues including medical/investment claims, copyright, personal data, and brand tone. Supports reading from file or direct content input.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute content checking

        Args:
            content: Post content text (optional if post_path provided)
            frontmatter: Post frontmatter (optional)
            vault_path: Path to Obsidian Vault (optional)
            post_path: Path to post Markdown file (optional)

        Returns:
            ToolExecutionResult with content check results
        """
        try:
            content = kwargs.get("content")
            frontmatter = kwargs.get("frontmatter")
            vault_path = kwargs.get("vault_path")
            post_path = kwargs.get("post_path")

            # If post_path provided, read content from file
            if post_path and vault_path:
                content, frontmatter = await self._read_content_from_file(vault_path, post_path)
                if not content:
                    return ToolExecutionResult(
                        success=False,
                        error=f"Failed to read content from {post_path}"
                    )

            if not content:
                return ToolExecutionResult(
                    success=False,
                    error="Either content or (vault_path + post_path) must be provided"
                )

            checker = ContentChecker()
            result = checker.check_content(content, frontmatter)

            return ToolExecutionResult(
                success=True,
                result=result
            )

        except Exception as e:
            logger.error(f"Content checker tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

    async def _read_content_from_file(
        self,
        vault_path: str,
        post_path: str
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Read content and frontmatter from Markdown file

        Args:
            vault_path: Path to Obsidian Vault
            post_path: Path to post Markdown file (relative to vault)

        Returns:
            Tuple of (content, frontmatter) or (None, None) if failed
        """
        try:
            from pathlib import Path
            import yaml
            import re

            vault = Path(vault_path).expanduser().resolve()
            file_path = vault / post_path

            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None, None

            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()

            # Parse frontmatter
            frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
            match = re.match(frontmatter_pattern, file_content, re.DOTALL)

            if match:
                frontmatter_str = match.group(1)
                content = match.group(2)
                try:
                    frontmatter = yaml.safe_load(frontmatter_str) or {}
                    return content, frontmatter
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse frontmatter YAML: {e}")
                    return file_content, {}
            else:
                return file_content, {}

        except Exception as e:
            logger.error(f"Failed to read content from file: {e}")
            return None, None


# Tool creation is handled in ig_series_manager_tool.py to avoid circular imports


"""
IG Frontmatter Validator Tool

Tool for validating frontmatter against Unified Frontmatter Schema v2.0.0
and calculating Readiness Score.
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
from backend.app.services.ig_obsidian.frontmatter_validator import FrontmatterValidator

logger = logging.getLogger(__name__)


class IGFrontmatterValidatorTool(MindscapeTool):
    """Tool for validating frontmatter against Unified Frontmatter Schema v2.0.0"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "frontmatter": {
                    "type": "object",
                    "description": "Frontmatter dictionary to validate"
                },
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault (optional, for reading frontmatter from file)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Path to post Markdown file (relative to vault, optional)"
                },
                "strict_mode": {
                    "type": "boolean",
                    "default": False,
                    "description": "Strict mode: all required fields must be present"
                },
                "domain": {
                    "type": "string",
                    "enum": ["ig", "wp", "seo", "book", "brand", "ops", "blog"],
                    "description": "Expected domain (if None, will use frontmatter['domain'])"
                }
            },
            required=[]
        )

        metadata = ToolMetadata(
            name="ig_frontmatter_validator_tool",
            description="Validate frontmatter against Unified Frontmatter Schema v2.0.0 and calculate Readiness Score. Supports IG Post, WordPress, Book, and other content types.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute frontmatter validation

        Args:
            frontmatter: Frontmatter dictionary to validate (optional if post_path provided)
            vault_path: Path to Obsidian Vault (optional)
            post_path: Path to post Markdown file (optional)
            strict_mode: Strict mode flag (default: False)
            domain: Expected domain (optional)

        Returns:
            ToolExecutionResult with validation results
        """
        try:
            frontmatter = kwargs.get("frontmatter")
            vault_path = kwargs.get("vault_path")
            post_path = kwargs.get("post_path")
            strict_mode = kwargs.get("strict_mode", False)
            domain = kwargs.get("domain")

            # If post_path provided, read frontmatter from file
            if post_path and vault_path:
                frontmatter = await self._read_frontmatter_from_file(vault_path, post_path)
                if not frontmatter:
                    return ToolExecutionResult(
                        success=False,
                        error=f"Failed to read frontmatter from {post_path}"
                    )

            if not frontmatter:
                return ToolExecutionResult(
                    success=False,
                    error="Either frontmatter or (vault_path + post_path) must be provided"
                )

            # Validate frontmatter
            validator = FrontmatterValidator(strict_mode=strict_mode)
            result = validator.validate(frontmatter, domain=domain)

            return ToolExecutionResult(
                success=True,
                result={
                    "is_valid": result["is_valid"],
                    "readiness_score": result["readiness_score"],
                    "missing_fields": result["missing_fields"],
                    "warnings": result["warnings"],
                    "errors": result["errors"]
                }
            )

        except Exception as e:
            logger.error(f"Frontmatter validator tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

    async def _read_frontmatter_from_file(self, vault_path: str, post_path: str) -> Optional[Dict[str, Any]]:
        """
        Read frontmatter from Markdown file

        Args:
            vault_path: Path to Obsidian Vault
            post_path: Path to post Markdown file (relative to vault)

        Returns:
            Frontmatter dictionary or None
        """
        try:
            from pathlib import Path
            import yaml
            import re

            vault = Path(vault_path).expanduser().resolve()
            file_path = vault / post_path

            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse frontmatter
            frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
            match = re.match(frontmatter_pattern, content, re.DOTALL)

            if match:
                frontmatter_str = match.group(1)
                try:
                    frontmatter = yaml.safe_load(frontmatter_str) or {}
                    return frontmatter
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse frontmatter YAML: {e}")
                    return None
            else:
                return {}

        except Exception as e:
            logger.error(f"Failed to read frontmatter from file: {e}")
            return None


def create_ig_obsidian_tools() -> list:
    """
    Create all IG + Obsidian integration tools

    Returns:
        List of IG + Obsidian MindscapeTool instances
    """
    from backend.app.services.tools.ig_obsidian.ig_vault_structure_tool import IGVaultStructureTool

    return [
        IGVaultStructureTool(),
        IGFrontmatterValidatorTool()
    ]



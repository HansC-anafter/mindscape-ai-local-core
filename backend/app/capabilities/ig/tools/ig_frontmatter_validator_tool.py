"""
IG Frontmatter Validator Tool

Tool for validating frontmatter against Unified Frontmatter Schema v2.0.0
and calculating Readiness Score.
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
import re

try:
    from backend.app.services.tools.base import MindscapeTool
    from backend.app.services.tools.schemas import (
        ToolMetadata,
        ToolExecutionResult,
        ToolDangerLevel,
        ToolSourceType,
        ToolInputSchema,
        ToolCategory
    )
except ImportError:
    # Fallback for cloud environment
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "mindscape-ai-local-core" / "backend"))
    from app.services.tools.base import MindscapeTool
    from app.services.tools.schemas import (
        ToolMetadata,
        ToolExecutionResult,
        ToolDangerLevel,
        ToolSourceType,
        ToolInputSchema,
        ToolCategory
    )

from capabilities.ig.services.frontmatter_validator import FrontmatterValidator
from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class IGFrontmatterValidatorTool(MindscapeTool):
    """Tool for validating frontmatter against Unified Frontmatter Schema v2.0.0"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "frontmatter": {
                    "type": "object",
                    "description": "Frontmatter dictionary to validate (optional if post_path provided)"
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier (required if post_path provided)"
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Custom workspace path (for backward compatibility/migration, not allowed in enterprise mode)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Path to post Markdown file (relative to workspace or Obsidian-style, optional)"
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
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute frontmatter validation

        Args:
            frontmatter: Frontmatter dictionary to validate (optional if post_path provided)
            workspace_id: Workspace identifier (required if post_path provided)
            workspace_path: Custom workspace path (for backward compatibility)
            post_path: Path to post Markdown file (optional)
            strict_mode: Strict mode flag (default: False)
            domain: Expected domain (optional)

        Returns:
            ToolExecutionResult with validation results
        """
        try:
            frontmatter = kwargs.get("frontmatter")
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")
            post_path = kwargs.get("post_path")
            strict_mode = kwargs.get("strict_mode", False)
            domain = kwargs.get("domain")

            # If post_path provided, read frontmatter from file
            if post_path:
                if not workspace_id and not workspace_path:
                    return ToolExecutionResult(
                        success=False,
                        error="Either workspace_id or workspace_path is required when post_path is provided"
                    )

                capability_code = "ig"
                tenant_id = os.getenv("TENANT_ID")

                if workspace_path:
                    allow_custom_path = not (tenant_id is not None)
                    storage = WorkspaceStorage.from_workspace_path(
                        workspace_id or "default",
                        capability_code,
                        workspace_path,
                        tenant_id=tenant_id,
                        allow_custom_path=allow_custom_path
                    )
                elif workspace_id:
                    storage = WorkspaceStorage(workspace_id, capability_code, tenant_id=tenant_id)
                else:
                    return ToolExecutionResult(
                        success=False,
                        error="Either workspace_id or workspace_path is required"
                    )

                frontmatter = await self._read_frontmatter_from_file(storage, post_path)
                if not frontmatter:
                    return ToolExecutionResult(
                        success=False,
                        error=f"Failed to read frontmatter from {post_path}"
                    )

            if not frontmatter:
                return ToolExecutionResult(
                    success=False,
                    error="Either frontmatter or (workspace_id + post_path) must be provided"
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

    async def _read_frontmatter_from_file(self, storage: WorkspaceStorage, post_path: str) -> Optional[Dict[str, Any]]:
        """
        Read frontmatter from Markdown file

        Args:
            storage: WorkspaceStorage instance
            post_path: Path to post Markdown file (relative to workspace or Obsidian-style)

        Returns:
            Frontmatter dictionary or None
        """
        try:
            # Resolve post path
            if post_path.startswith("20-Posts/") or post_path.startswith("posts/"):
                parts = post_path.split("/")
                if len(parts) >= 2:
                    post_folder = parts[-2]
                    post_file = parts[-1] if parts[-1].endswith(".md") else "post.md"
                else:
                    post_folder = parts[0].replace(".md", "")
                    post_file = "post.md"
            else:
                post_folder = post_path.replace(".md", "").replace("/", "")
                post_file = "post.md"

            if "_" in post_folder:
                post_slug = post_folder.split("_")[-1]
            else:
                post_slug = post_folder

            post_dir = storage.get_post_path(post_slug)
            file_path = post_dir / post_file

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


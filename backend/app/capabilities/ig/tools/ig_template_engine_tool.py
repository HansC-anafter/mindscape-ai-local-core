"""
IG Template Engine Tool

Tool for applying templates to generate IG posts with multiple variants.
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
from capabilities.ig.services.template_engine import IGTemplateEngine

logger = logging.getLogger(__name__)


class IGTemplateEngineTool(MindscapeTool):
    """Tool for applying templates to generate IG posts"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["load", "generate"],
                    "description": "Action to perform: load=load template, generate=generate posts"
                },
                "template_type": {
                    "type": "string",
                    "enum": ["carousel", "reel", "story"],
                    "description": "Template type (required for load action)"
                },
                "style_tone": {
                    "type": "string",
                    "enum": ["high_brand", "friendly", "coach", "sponsored"],
                    "default": "friendly",
                    "description": "Style tone (required for load action)"
                },
                "purpose": {
                    "type": "string",
                    "enum": ["save", "comment", "dm", "share"],
                    "default": "save",
                    "description": "Post purpose (required for load action)"
                },
                "template": {
                    "type": "object",
                    "description": "Template dictionary (required for generate action)"
                },
                "source_content": {
                    "type": "string",
                    "description": "Source content to transform (required for generate action)"
                },
                "generate_variants": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to generate multiple variants"
                }
            },
            required=["action"]
        )

        metadata = ToolMetadata(
            name="ig_template_engine_tool",
            description="Apply templates to generate IG posts with multiple variants. Supports carousel, reel, and story templates with different style tones and purposes.",
            input_schema=input_schema,
            category=ToolCategory.CONTENT,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute template engine action

        Args:
            action: Action to perform (load, generate)
            template_type: Template type (for load action)
            style_tone: Style tone (for load action)
            purpose: Purpose (for load action)
            template: Template dictionary (for generate action)
            source_content: Source content (for generate action)
            generate_variants: Whether to generate variants (for generate action)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")

            if action not in ["load", "generate"]:
                return ToolExecutionResult(
                    success=False,
                    error=f"Invalid action: {action}. Must be 'load' or 'generate'"
                )

            engine = IGTemplateEngine()

            if action == "load":
                template_type = kwargs.get("template_type")
                style_tone = kwargs.get("style_tone", "friendly")
                purpose = kwargs.get("purpose", "save")

                if not template_type:
                    return ToolExecutionResult(
                        success=False,
                        error="template_type is required for load action"
                    )

                template = engine.load_template(template_type, style_tone, purpose)

                return ToolExecutionResult(
                    success=True,
                    result={
                        "template": template
                    }
                )

            elif action == "generate":
                template = kwargs.get("template")
                source_content = kwargs.get("source_content")
                generate_variants = kwargs.get("generate_variants", True)

                if not template:
                    return ToolExecutionResult(
                        success=False,
                        error="template is required for generate action"
                    )

                if not source_content:
                    return ToolExecutionResult(
                        success=False,
                        error="source_content is required for generate action"
                    )

                result = engine.generate_posts(template, source_content, generate_variants)

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

        except Exception as e:
            logger.error(f"Template engine tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


# Tool creation is handled in ig_hashtag_manager_tool.py to avoid circular imports


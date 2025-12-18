"""
IG Interaction Templates Tool

Tool for managing interaction templates including common comment replies,
DM scripts, and tone switching.
"""
import logging
from typing import Dict, Any, List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolExecutionResult,
    ToolDangerLevel,
    ToolSourceType,
    ToolInputSchema,
    ToolCategory
)
from backend.app.services.ig_obsidian.interaction_templates import InteractionTemplates

logger = logging.getLogger(__name__)


class IGInteractionTemplatesTool(MindscapeTool):
    """Tool for managing interaction templates"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["create", "get", "list", "render", "suggest", "switch_tone", "update"],
                    "description": "Action to perform"
                },
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault"
                },
                "template_id": {
                    "type": "string",
                    "description": "Template identifier"
                },
                "template_type": {
                    "type": "string",
                    "enum": ["comment_reply", "dm_script", "story_reply"],
                    "description": "Type of template"
                },
                "content": {
                    "type": "string",
                    "description": "Template content (supports {{variable}} placeholders)"
                },
                "tone": {
                    "type": "string",
                    "enum": ["friendly", "professional", "casual", "formal"],
                    "description": "Tone of the template"
                },
                "category": {
                    "type": "string",
                    "description": "Category (e.g., 'greeting', 'product_inquiry', 'complaint')"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tags for categorization"
                },
                "variables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of variable names used in template"
                },
                "render_variables": {
                    "type": "object",
                    "description": "Dictionary of variable values for rendering (e.g., {'name': 'John'})"
                },
                "context": {
                    "type": "string",
                    "description": "Context description for template suggestion"
                },
                "new_tone": {
                    "type": "string",
                    "enum": ["friendly", "professional", "casual", "formal"],
                    "description": "New tone for switch_tone action"
                },
                "updates": {
                    "type": "object",
                    "description": "Dictionary of fields to update"
                }
            },
            required=["action", "vault_path"]
        )

        metadata = ToolMetadata(
            name="ig_interaction_templates_tool",
            description="Manage interaction templates including common comment replies, DM scripts, tone switching, and template categorization for customer engagement.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute interaction templates action

        Args:
            action: Action to perform
            vault_path: Path to Obsidian Vault
            template_id: Template identifier
            template_type: Type of template
            content: Template content
            tone: Tone of template
            category: Category
            tags: Tags list
            variables: Variables list
            render_variables: Variables for rendering
            context: Context for suggestion
            new_tone: New tone for switch_tone
            updates: Updates dictionary

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")
            vault_path = kwargs.get("vault_path")

            if not vault_path:
                return ToolExecutionResult(
                    success=False,
                    error="vault_path is required"
                )

            templates = InteractionTemplates(vault_path)

            if action == "create":
                template_id = kwargs.get("template_id")
                template_type = kwargs.get("template_type")
                content = kwargs.get("content")
                tone = kwargs.get("tone")
                category = kwargs.get("category")
                tags = kwargs.get("tags")
                variables = kwargs.get("variables")

                if not all([template_id, template_type, content]):
                    return ToolExecutionResult(
                        success=False,
                        error="template_id, template_type, and content are required for create action"
                    )

                template = templates.create_template(
                    template_id=template_id,
                    template_type=template_type,
                    content=content,
                    tone=tone,
                    category=category,
                    tags=tags,
                    variables=variables
                )

                return ToolExecutionResult(
                    success=True,
                    result={"template": template}
                )

            elif action == "get":
                template_id = kwargs.get("template_id")

                if not template_id:
                    return ToolExecutionResult(
                        success=False,
                        error="template_id is required for get action"
                    )

                template = templates.get_template(template_id)

                if not template:
                    return ToolExecutionResult(
                        success=False,
                        error=f"Template {template_id} not found"
                    )

                return ToolExecutionResult(
                    success=True,
                    result={"template": template}
                )

            elif action == "list":
                template_type = kwargs.get("template_type")
                tone = kwargs.get("tone")
                category = kwargs.get("category")
                tags = kwargs.get("tags")

                template_list = templates.list_templates(
                    template_type=template_type,
                    tone=tone,
                    category=category,
                    tags=tags
                )

                return ToolExecutionResult(
                    success=True,
                    result={"templates": template_list}
                )

            elif action == "render":
                template_id = kwargs.get("template_id")
                render_variables = kwargs.get("render_variables", {})

                if not template_id:
                    return ToolExecutionResult(
                        success=False,
                        error="template_id is required for render action"
                    )

                rendered = templates.render_template(
                    template_id=template_id,
                    variables=render_variables
                )

                return ToolExecutionResult(
                    success=True,
                    result={"rendered_content": rendered}
                )

            elif action == "suggest":
                context = kwargs.get("context")
                template_type = kwargs.get("template_type")
                tone = kwargs.get("tone")

                if not context:
                    return ToolExecutionResult(
                        success=False,
                        error="context is required for suggest action"
                    )

                suggested = templates.suggest_template(
                    context=context,
                    template_type=template_type,
                    tone=tone
                )

                return ToolExecutionResult(
                    success=True,
                    result={"suggested_template": suggested}
                )

            elif action == "switch_tone":
                template_id = kwargs.get("template_id")
                new_tone = kwargs.get("new_tone")

                if not all([template_id, new_tone]):
                    return ToolExecutionResult(
                        success=False,
                        error="template_id and new_tone are required for switch_tone action"
                    )

                new_template = templates.switch_tone(
                    template_id=template_id,
                    new_tone=new_tone
                )

                return ToolExecutionResult(
                    success=True,
                    result={"template": new_template}
                )

            elif action == "update":
                template_id = kwargs.get("template_id")
                updates = kwargs.get("updates")

                if not all([template_id, updates]):
                    return ToolExecutionResult(
                        success=False,
                        error="template_id and updates are required for update action"
                    )

                updated = templates.update_template(
                    template_id=template_id,
                    updates=updates
                )

                return ToolExecutionResult(
                    success=True,
                    result={"template": updated}
                )

            else:
                return ToolExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Interaction templates tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


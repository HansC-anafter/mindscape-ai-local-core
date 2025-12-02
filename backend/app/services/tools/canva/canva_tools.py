"""
Canva tools for Mindscape AI

Implements MindscapeTool interface for Canva Connect API operations.
Each tool corresponds to a specific Canva operation.
"""

from typing import Dict, Any, List, Optional
import logging

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolCategory,
    ToolSourceType,
    ToolDangerLevel,
    create_simple_tool_metadata,
)
from backend.app.services.tools.canva.canva_client import CanvaAPIClient, CanvaAPIError

logger = logging.getLogger(__name__)


class CanvaCreateDesignTool(MindscapeTool):
    """
    Create a new Canva design from a template
    """

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="canva.create_design_from_template",
            description="Create a new Canva design from a template. Returns design ID and details.",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.BUILTIN,
            danger_level=ToolDangerLevel.MEDIUM,
            properties={
                "template_id": {
                    "type": "string",
                    "description": "Template ID to create design from",
                },
                "brand_id": {
                    "type": "string",
                    "description": "Optional brand ID for the design",
                },
                "title": {
                    "type": "string",
                    "description": "Optional design title",
                },
            },
            required=["template_id"],
        )
        super().__init__(metadata)
        self.connection = connection
        self.client = CanvaAPIClient(connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute: Create design from template

        Args:
            input_data: Validated input parameters
                - template_id: Template ID (required)
                - brand_id: Optional brand ID
                - title: Optional design title

        Returns:
            {
                "success": True,
                "design": {
                    "id": "...",
                    "title": "...",
                    ...
                }
            }
        """
        try:
            template_id = input_data["template_id"]
            brand_id = input_data.get("brand_id")
            title = input_data.get("title")

            design = await self.client.create_design(
                template_id=template_id,
                brand_id=brand_id,
                title=title,
            )

            return {
                "success": True,
                "design": {
                    "id": design.id,
                    "title": design.title,
                    "brand_id": design.brand_id,
                    "template_id": design.template_id,
                    "width": design.width,
                    "height": design.height,
                    "url": design.url,
                },
            }
        except CanvaAPIError as e:
            logger.error(f"Canva API error in create_design: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": e.status_code,
            }
        except Exception as e:
            logger.error(f"Unexpected error in create_design: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }


class CanvaUpdateTextTool(MindscapeTool):
    """
    Update text blocks in a Canva design
    """

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="canva.update_text_blocks",
            description="Update text blocks in a Canva design. Can update single or multiple text blocks.",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.BUILTIN,
            danger_level=ToolDangerLevel.MEDIUM,
            properties={
                "design_id": {
                    "type": "string",
                    "description": "Design ID to update",
                },
                "text_blocks": {
                    "type": "array",
                    "description": "List of text block updates",
                    "items": {
                        "type": "object",
                        "properties": {
                            "block_id": {
                                "type": "string",
                                "description": "Text block ID to update",
                            },
                            "text": {
                                "type": "string",
                                "description": "New text content",
                            },
                        },
                        "required": ["block_id", "text"],
                    },
                },
            },
            required=["design_id", "text_blocks"],
        )
        super().__init__(metadata)
        self.connection = connection
        self.client = CanvaAPIClient(connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute: Update text blocks

        Args:
            input_data: Validated input parameters
                - design_id: Design ID (required)
                - text_blocks: List of text block updates (required)
                  Each update: {"block_id": "...", "text": "..."}

        Returns:
            {
                "success": True,
                "updated_blocks": [...]
            }
        """
        try:
            design_id = input_data["design_id"]
            text_blocks = input_data["text_blocks"]

            if not isinstance(text_blocks, list) or len(text_blocks) == 0:
                return {
                    "success": False,
                    "error": "text_blocks must be a non-empty list",
                }

            if len(text_blocks) == 1:
                block = text_blocks[0]
                updated_block = await self.client.update_text_block(
                    design_id=design_id,
                    block_id=block["block_id"],
                    text=block["text"],
                )
                updated_blocks = [updated_block]
            else:
                updated_blocks = await self.client.update_text_blocks(
                    design_id=design_id,
                    text_blocks=text_blocks,
                )

            return {
                "success": True,
                "updated_blocks": [
                    {
                        "id": block.id,
                        "text": block.text,
                    }
                    for block in updated_blocks
                ],
            }
        except CanvaAPIError as e:
            logger.error(f"Canva API error in update_text_blocks: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": e.status_code,
            }
        except Exception as e:
            logger.error(f"Unexpected error in update_text_blocks: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }


class CanvaListTemplatesTool(MindscapeTool):
    """
    List available Canva templates
    """

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="canva.list_templates",
            description="List available Canva templates. Can filter by brand and paginate results.",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.BUILTIN,
            danger_level=ToolDangerLevel.LOW,
            properties={
                "brand_id": {
                    "type": "string",
                    "description": "Optional brand ID to filter templates",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of templates to return",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset",
                    "default": 0,
                    "minimum": 0,
                },
            },
            required=[],
        )
        super().__init__(metadata)
        self.connection = connection
        self.client = CanvaAPIClient(connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute: List templates

        Args:
            input_data: Validated input parameters
                - brand_id: Optional brand ID filter
                - limit: Maximum results (default: 20)
                - offset: Pagination offset (default: 0)

        Returns:
            {
                "success": True,
                "templates": [...],
                "count": 10
            }
        """
        try:
            brand_id = input_data.get("brand_id")
            limit = input_data.get("limit", 20)
            offset = input_data.get("offset", 0)

            templates = await self.client.list_templates(
                brand_id=brand_id,
                limit=limit,
                offset=offset,
            )

            return {
                "success": True,
                "templates": [
                    {
                        "id": template.id,
                        "title": template.title,
                        "description": template.description,
                        "width": template.width,
                        "height": template.height,
                        "thumbnail_url": template.thumbnail_url,
                    }
                    for template in templates
                ],
                "count": len(templates),
            }
        except CanvaAPIError as e:
            logger.error(f"Canva API error in list_templates: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": e.status_code,
            }
        except Exception as e:
            logger.error(f"Unexpected error in list_templates: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }


class CanvaExportDesignTool(MindscapeTool):
    """
    Export a Canva design as image or PDF
    """

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="canva.export_design",
            description="Export a Canva design as PNG, JPG, or PDF. Returns export URL and status.",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.BUILTIN,
            danger_level=ToolDangerLevel.LOW,
            properties={
                "design_id": {
                    "type": "string",
                    "description": "Design ID to export",
                },
                "format": {
                    "type": "string",
                    "description": "Export format",
                    "enum": ["PNG", "JPG", "PDF"],
                    "default": "PNG",
                },
                "scale": {
                    "type": "number",
                    "description": "Export scale factor (0.1 to 4.0)",
                    "minimum": 0.1,
                    "maximum": 4.0,
                },
            },
            required=["design_id"],
        )
        super().__init__(metadata)
        self.connection = connection
        self.client = CanvaAPIClient(connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute: Export design

        Args:
            input_data: Validated input parameters
                - design_id: Design ID (required)
                - format: Export format (PNG, JPG, PDF, default: PNG)
                - scale: Optional scale factor (0.1-4.0)

        Returns:
            {
                "success": True,
                "export": {
                    "url": "...",
                    "status": "...",
                    ...
                }
            }
        """
        try:
            design_id = input_data["design_id"]
            format = input_data.get("format", "PNG")
            scale = input_data.get("scale")

            export_info = await self.client.export_design(
                design_id=design_id,
                format=format,
                scale=scale,
            )

            return {
                "success": True,
                "export": export_info,
            }
        except CanvaAPIError as e:
            logger.error(f"Canva API error in export_design: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": e.status_code,
            }
        except Exception as e:
            logger.error(f"Unexpected error in export_design: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
            }


def create_canva_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Create all Canva tools for a connection

    Args:
        connection: ToolConnection instance

    Returns:
        List of Canva tool instances
    """
    return [
        CanvaCreateDesignTool(connection),
        CanvaUpdateTextTool(connection),
        CanvaListTemplatesTool(connection),
        CanvaExportDesignTool(connection),
    ]


def get_canva_tool_by_name(tool_name: str, connection: ToolConnection) -> Optional[MindscapeTool]:
    """
    Get a specific Canva tool by name

    Args:
        tool_name: Tool name (e.g., "canva.create_design_from_template")
        connection: ToolConnection instance

    Returns:
        MindscapeTool instance or None if not found
    """
    tool_map = {
        "canva.create_design_from_template": CanvaCreateDesignTool,
        "canva.update_text_blocks": CanvaUpdateTextTool,
        "canva.list_templates": CanvaListTemplatesTool,
        "canva.export_design": CanvaExportDesignTool,
    }

    tool_class = tool_map.get(tool_name)
    if tool_class:
        return tool_class(connection)
    return None

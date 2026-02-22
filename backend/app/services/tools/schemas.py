"""
Tool Schema Definitions

Defines standardized schemas for the Mindscape AI tool system, including:
- Tool metadata (name, description, schema, category)
- JSON Schema compatible input specifications
- Tool category and danger level enumerations

Design principles:
- Framework-neutral: not tied to any specific tool ecosystem
- JSON Schema compatible: supports LangChain/MCP conversion
- Uses Pydantic v2 API
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Literal
from enum import Enum


class ToolInputSchema(BaseModel):
    """
    Tool input parameter schema (aligned with JSON Schema)

    Example:
        schema = ToolInputSchema(
            type="object",
            properties={
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10
                }
            },
            required=["query"]
        )
    """

    type: Literal["object"] = "object"
    properties: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Parameter definitions"
    )
    required: List[str] = Field(
        default_factory=list, description="Required parameter names"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"],
            }
        }


class ToolSourceType(str, Enum):
    """Tool source type"""

    BUILTIN = "builtin"  # Built-in tools (WordPress, Notion, etc.)
    LANGCHAIN = "langchain"  # LangChain community tools
    MCP = "mcp"  # MCP protocol tools
    CUSTOM = "custom"  # Custom tools


class ToolCategory(str, Enum):
    """Tool category"""

    CONTENT = "content"  # Content creation/management
    DATA = "data"  # Data query/search
    AUTOMATION = "automation"  # Automation/scripting
    COMMUNICATION = "communication"  # Communication/notification
    ANALYSIS = "analysis"  # Analysis/computation


class ToolDangerLevel(str, Enum):
    """Tool danger level"""

    LOW = "low"  # Read-only operations
    MEDIUM = "medium"  # Write operations
    HIGH = "high"  # Modify/delete operations
    CRITICAL = "critical"  # Execution/system operations


class ToolMetadata(BaseModel):
    """
    Tool metadata (aligned with LangChain BaseTool)

    This schema can be bidirectionally converted with LangChain BaseTool,
    and also maps to MCP tool spec.

    Example:
        metadata = ToolMetadata(
            name="search_wikipedia",
            description="Search Wikipedia for information",
            input_schema=ToolInputSchema(...),
            category=ToolCategory.DATA,
            source_type=ToolSourceType.LANGCHAIN,
            provider="wikipedia"
        )
    """

    # Core fields (aligned with LangChain BaseTool)
    name: str = Field(
        ...,
        description="Tool name (unique identifier, use snake_case)",
        pattern=r"^[a-z][a-z0-9_.]*$",
    )
    description: str = Field(
        ...,
        description="Tool description (read by LLM, must clearly describe functionality)",
        min_length=10,
        max_length=500,
    )
    input_schema: ToolInputSchema = Field(
        ..., description="Input parameter JSON Schema"
    )
    return_direct: bool = Field(
        default=False,
        description="Whether to return result directly to user (bypass LLM processing)",
    )

    # Mindscape extension fields
    category: ToolCategory = Field(
        default=ToolCategory.AUTOMATION, description="Tool category"
    )
    source_type: ToolSourceType = Field(..., description="Tool source type")
    provider: Optional[str] = Field(
        default=None,
        description="Tool provider (e.g. 'wordpress', 'github', 'wikipedia')",
    )
    danger_level: ToolDangerLevel = Field(
        default=ToolDangerLevel.LOW, description="Danger level"
    )

    # Optional fields
    version: Optional[str] = Field(default="1.0.0", description="Tool version")
    tags: List[str] = Field(
        default_factory=list, description="Tags (for search and categorization)"
    )
    examples: List[Dict[str, Any]] = Field(
        default_factory=list, description="Usage examples"
    )

    # MCP related (reserved)
    mcp_server_id: Optional[str] = Field(
        default=None, description="MCP server ID (if this is an MCP tool)"
    )

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "name": "search_wikipedia",
                "description": "Search Wikipedia for information on any topic",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"],
                },
                "category": "data",
                "source_type": "langchain",
                "provider": "wikipedia",
                "danger_level": "low",
                "return_direct": False,
            }
        }

    def to_langchain_schema(self) -> Dict[str, Any]:
        """
        Convert to LangChain tool schema.

        Returns:
            Schema dict usable by LangChain.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_dump(),
            "return_direct": self.return_direct,
        }

    def to_mcp_schema(self) -> Dict[str, Any]:
        """
        Convert to MCP tool schema.

        Returns:
            MCP protocol tool info.
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema.model_dump(),
        }

    def is_dangerous(self) -> bool:
        """Check whether this is a dangerous operation."""
        return self.danger_level in [ToolDangerLevel.HIGH, ToolDangerLevel.CRITICAL]

    def requires_confirmation(self) -> bool:
        """Check whether user confirmation is required."""
        return self.danger_level in [
            ToolDangerLevel.MEDIUM,
            ToolDangerLevel.HIGH,
            ToolDangerLevel.CRITICAL,
        ]


class ToolExecutionResult(BaseModel):
    """Tool execution result"""

    success: bool = Field(..., description="Whether execution succeeded")
    result: Any = Field(default=None, description="Execution result")
    error: Optional[str] = Field(default=None, description="Error message")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (execution time, token usage, etc.)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "result": "Wikipedia summary of...",
                "error": None,
                "metadata": {"execution_time_ms": 250, "source": "wikipedia"},
            }
        }


# Convenience functions
def create_simple_tool_metadata(
    name: str,
    description: str,
    parameters: Dict[str, Dict[str, Any]],
    required: List[str] = None,
    source_type: ToolSourceType = ToolSourceType.BUILTIN,
    **kwargs
) -> ToolMetadata:
    """
    Quickly create simple tool metadata.

    Args:
        name: Tool name
        description: Description
        parameters: Parameter definitions {"param_name": {"type": "string", "description": "..."}}
        required: Required parameter list
        source_type: Source type
        **kwargs: Other ToolMetadata fields

    Returns:
        ToolMetadata instance

    Example:
        metadata = create_simple_tool_metadata(
            name="create_post",
            description="Create a new WordPress post",
            parameters={
                "title": {"type": "string", "description": "Post title"},
                "content": {"type": "string", "description": "Post content"}
            },
            required=["title", "content"],
            category=ToolCategory.CONTENT,
            danger_level=ToolDangerLevel.MEDIUM
        )
    """
    input_schema = ToolInputSchema(
        type="object", properties=parameters, required=required or []
    )

    return ToolMetadata(
        name=name,
        description=description,
        input_schema=input_schema,
        source_type=source_type,
        **kwargs
    )

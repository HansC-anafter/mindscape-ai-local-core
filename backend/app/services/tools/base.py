"""
Tool base classes and interface definitions

Defines Mindscape AI's tool abstraction layer, including:
- ToolConnection: Tool connection configuration
- Tool: Legacy tool base class (backward compatible)
- MindscapeTool: New tool abstract base class, supports LangChain/MCP conversion

Design principles:
- Backward compatible: Keep legacy Tool class
- Framework neutral: Support multiple tool ecosystem conversions
- Async first: All executions are asynchronous
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolExecutionResult,
    ToolDangerLevel,
    ToolSourceType
)

logger = logging.getLogger(__name__)


class ToolConnection:
    """Tool connection configuration"""

    def __init__(
        self,
        id: str,
        tool_type: str,
        connection_type: str = "local",  # "local" or "remote"
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        oauth_token: Optional[str] = None,
        base_url: Optional[str] = None,
        remote_cluster_url: Optional[str] = None,
        remote_connection_id: Optional[str] = None,
        name: str = "",
        description: Optional[str] = None,
        associated_roles: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.id = id
        self.tool_type = tool_type
        self.connection_type = connection_type
        self.api_key = api_key
        self.api_secret = api_secret
        self.oauth_token = oauth_token
        self.base_url = base_url
        self.remote_cluster_url = remote_cluster_url
        self.remote_connection_id = remote_connection_id
        self.name = name or tool_type
        self.description = description
        self.associated_roles = associated_roles or []
        self.config = config or {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()


class Tool(ABC):
    """Base class for all tools"""

    # High-risk actions that require user confirmation
    HIGH_RISK_ACTIONS: List[str] = []

    def __init__(self, connection: ToolConnection):
        self.connection = connection
        self.tool_type = connection.tool_type
        self.connection_type = connection.connection_type

    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool action"""
        pass

    @abstractmethod
    def get_available_actions(self) -> List[str]:
        """Get list of available actions for this tool"""
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Validate if connection is working"""
        pass

    def is_high_risk_action(self, action: str) -> bool:
        """Check if action requires user confirmation"""
        return action in self.HIGH_RISK_ACTIONS

    def requires_confirmation(self, action: str) -> bool:
        """Alias for is_high_risk_action"""
        return self.is_high_risk_action(action)


# ========== New Tool Interface ==========

class MindscapeTool(ABC):
    """
    Mindscape Tool abstract base class (new version)

    Design principles:
    1. Remain framework-neutral, no dependencies on specific frameworks
    2. Can be easily converted to LangChain BaseTool or MCP Tool
    3. Supports both synchronous and asynchronous execution

    Example:
        class MyTool(MindscapeTool):
            def __init__(self):
                metadata = create_simple_tool_metadata(
                    name="my_tool",
                    description="My custom tool",
                    parameters={"input": {"type": "string"}},
                    required=["input"]
                )
                super().__init__(metadata)

            async def execute(self, input: str):
                return f"Processed: {input}"
    """

    def __init__(self, metadata: ToolMetadata):
        """
        Initialize tool

        Args:
            metadata: Tool metadata
        """
        self.metadata = metadata
        self._validate_metadata()

    def _validate_metadata(self):
        """Validate metadata completeness"""
        if not self.metadata.name:
            raise ValueError("Tool name is required")
        if not self.metadata.description:
            raise ValueError("Tool description is required")
        if not self.metadata.input_schema:
            raise ValueError("Tool input_schema is required")

    @property
    def name(self) -> str:
        """Tool name"""
        return self.metadata.name

    @property
    def description(self) -> str:
        """Tool description"""
        return self.metadata.description

    @property
    def source_type(self) -> ToolSourceType:
        """Tool source type"""
        return self.metadata.source_type

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute tool

        Args:
            **kwargs: Parameters defined by input_schema

        Returns:
            Tool execution result (any type)

        Raises:
            ValueError: Parameter validation failed
            RuntimeError: Execution failed
        """
        pass

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        """
        Validate input parameters against schema

        Args:
            **kwargs: Input parameters

        Returns:
            Validated parameters

        Raises:
            ValueError: Validation failure
        """
        schema = self.metadata.input_schema

        # Check required parameters
        for required_param in schema.required:
            if required_param not in kwargs:
                raise ValueError(
                    f"Missing required parameter: {required_param}"
                )

        # Validate parameter types (basic validation)
        validated = {}
        for param_name, param_value in kwargs.items():
            if param_name not in schema.properties:
                logger.warning(
                    f"Unknown parameter '{param_name}' for tool '{self.name}'"
                )
                continue

            # TODO: Add stricter type validation (optional)
            validated[param_name] = param_value

        return validated

    async def safe_execute(self, **kwargs) -> ToolExecutionResult:
        """
        Safely execute tool with error handling and result wrapping

        Args:
            **kwargs: Tool parameters

        Returns:
            ToolExecutionResult
        """
        import time
        start_time = time.time()

        try:
            # Validate input parameters
            validated = self.validate_input(**kwargs)

            # Execute the tool
            result = await self.execute(**validated)

            execution_time = int((time.time() - start_time) * 1000)

            return ToolExecutionResult(
                success=True,
                result=result,
                error=None,
                metadata={
                    "tool_name": self.name,
                    "execution_time_ms": execution_time,
                    "source_type": self.source_type
                }
            )

        except ValueError as e:
            # Parameter validation error
            logger.error(f"Tool {self.name} validation error: {e}")
            return ToolExecutionResult(
                success=False,
                result=None,
                error=f"Validation error: {str(e)}",
                metadata={"tool_name": self.name}
            )

        except Exception as e:
            # Execution error
            logger.error(f"Tool {self.name} execution error: {e}")
            return ToolExecutionResult(
                success=False,
                result=None,
                error=f"Execution error: {str(e)}",
                metadata={"tool_name": self.name}
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization

        Returns:
            Dictionary representation of the tool
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.metadata.input_schema.model_dump(),
            "metadata": self.metadata.model_dump()
        }

    def to_langchain_tool(self):
        """
        Convert to LangChain BaseTool

        Returns:
            LangChain StructuredTool instance

        Raises:
            ImportError: If LangChain is not installed

        Example:
            >>> tool = WordPressListPostsTool(connection)
            >>> lc_tool = tool.to_langchain_tool()
            >>> result = await lc_tool.ainvoke({"per_page": 10})
        """
        try:
            from backend.app.services.tools.adapters.langchain_adapter import to_langchain
            return to_langchain(self)
        except ImportError:
            raise ImportError(
                "LangChain is not installed. "
                "Install with: pip install 'langchain>=0.1.0' 'langchain-core>=0.1.0'"
            )

    def to_mcp_tool(self):
        """
        Convert to MCP Tool

        Raises:
            NotImplementedError: MCP support not available
        """
        raise NotImplementedError(
            "MCP support not installed. "
            "Install with: pip install 'mindscape-ai[mcp]'"
        )

    def __repr__(self) -> str:
        return f"<MindscapeTool: {self.name} ({self.source_type})>"

    def __str__(self) -> str:
        return f"{self.name}: {self.description[:50]}..."


# Convenience functions
def create_tool_from_function(
    func,
    name: str,
    description: str,
    source_type: ToolSourceType = ToolSourceType.CUSTOM
) -> MindscapeTool:
    """
    Create tool from function (simplified version)

    Args:
        func: Async function
        name: Tool name
        description: Description
        source_type: Source type

    Returns:
        MindscapeTool instance

    Example:
        async def my_func(query: str):
            return f"Result for {query}"

        tool = create_tool_from_function(
            my_func,
            name="my_tool",
            description="My custom tool"
        )
    """
    import inspect
    from backend.app.services.tools.schemas import create_simple_tool_metadata

    # Infer parameters from function signature
    sig = inspect.signature(func)
    parameters = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ['self', 'cls']:
            continue

        param_type = "string"  # Default type
        if param.annotation != inspect.Parameter.empty:
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == bool:
                param_type = "boolean"
            elif param.annotation == float:
                param_type = "number"

        parameters[param_name] = {
            "type": param_type,
            "description": f"Parameter {param_name}"
        }

        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    # Create metadata
    metadata = create_simple_tool_metadata(
        name=name,
        description=description,
        parameters=parameters,
        required=required,
        source_type=source_type
    )

    # Create dynamic tool class
    class DynamicTool(MindscapeTool):
        async def execute(self, **kwargs):
            return await func(**kwargs)

    return DynamicTool(metadata)

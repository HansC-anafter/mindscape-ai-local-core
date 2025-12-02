"""
工具基礎類別和接口定義

定義 Mindscape AI 的工具抽象層，包括：
- ToolConnection: 工具連接配置
- Tool: 舊版工具基礎類(向後兼容)
- MindscapeTool: 新版工具抽象基礎類，支援 LangChain/MCP 轉換

設計原則：
- 向後兼容：保留舊 Tool 類
- 框架中立：支援多種工具生態轉換
- 異步優先：所有執行都是異步
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


# ========== 新版工具介面 ==========

class MindscapeTool(ABC):
    """
    Mindscape 工具抽象類(新版)

    設計原則：
    1. 保持中立，不依賴任何特定框架
    2. 可以輕鬆轉換成 LangChain BaseTool 或 MCP Tool
    3. 支援同步和異步執行

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
        初始化工具

        Args:
            metadata: 工具元數據
        """
        self.metadata = metadata
        self._validate_metadata()

    def _validate_metadata(self):
        """驗證 metadata 完整性"""
        if not self.metadata.name:
            raise ValueError("Tool name is required")
        if not self.metadata.description:
            raise ValueError("Tool description is required")
        if not self.metadata.input_schema:
            raise ValueError("Tool input_schema is required")

    @property
    def name(self) -> str:
        """工具名稱"""
        return self.metadata.name

    @property
    def description(self) -> str:
        """工具描述"""
        return self.metadata.description

    @property
    def source_type(self) -> ToolSourceType:
        """工具來源類型"""
        return self.metadata.source_type

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        執行工具

        Args:
            **kwargs: 根據 input_schema 定義的參數

        Returns:
            工具執行結果(任意類型)

        Raises:
            ValueError: 參數驗證失敗
            RuntimeError: 執行失敗
        """
        pass

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        """
        驗證輸入參數是否符合 schema

        Args:
            **kwargs: 輸入參數

        Returns:
            驗證後的參數

        Raises:
            ValueError: 驗證失敗
        """
        schema = self.metadata.input_schema

        # 檢查必填參數
        for required_param in schema.required:
            if required_param not in kwargs:
                raise ValueError(
                    f"Missing required parameter: {required_param}"
                )

        # 檢查參數類型(基礎驗證)
        validated = {}
        for param_name, param_value in kwargs.items():
            if param_name not in schema.properties:
                logger.warning(
                    f"Unknown parameter '{param_name}' for tool '{self.name}'"
                )
                continue

            # TODO: 更嚴格的類型驗證(可選)
            validated[param_name] = param_value

        return validated

    async def safe_execute(self, **kwargs) -> ToolExecutionResult:
        """
        安全執行工具(包含錯誤處理和結果包裝)

        Args:
            **kwargs: 工具參數

        Returns:
            ToolExecutionResult
        """
        import time
        start_time = time.time()

        try:
            # 驗證輸入
            validated = self.validate_input(**kwargs)

            # 執行工具
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
            # 參數驗證錯誤
            logger.error(f"Tool {self.name} validation error: {e}")
            return ToolExecutionResult(
                success=False,
                result=None,
                error=f"Validation error: {str(e)}",
                metadata={"tool_name": self.name}
            )

        except Exception as e:
            # 執行錯誤
            logger.error(f"Tool {self.name} execution error: {e}")
            return ToolExecutionResult(
                success=False,
                result=None,
                error=f"Execution error: {str(e)}",
                metadata={"tool_name": self.name}
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        轉換成字典(用於序列化)

        Returns:
            工具的字典表示
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.metadata.input_schema.model_dump(),
            "metadata": self.metadata.model_dump()
        }

    def to_langchain_tool(self):
        """
        轉換成 LangChain BaseTool

        這個方法在 Phase 1 實作(需要 LangChain 依賴)
        轉換為 LangChain StructuredTool

        Returns:
            LangChain StructuredTool 實例

        Raises:
            ImportError: 如果 LangChain 未安裝

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
        轉換成 MCP Tool

        這個方法在 Phase 2 實作(需要 MCP 依賴)

        Raises:
            NotImplementedError: 需要安裝 MCP 支援
        """
        raise NotImplementedError(
            "MCP support not installed. "
            "Install with: pip install 'mindscape-ai[mcp]'"
        )

    def __repr__(self) -> str:
        return f"<MindscapeTool: {self.name} ({self.source_type})>"

    def __str__(self) -> str:
        return f"{self.name}: {self.description[:50]}..."


# 便捷函式
def create_tool_from_function(
    func,
    name: str,
    description: str,
    source_type: ToolSourceType = ToolSourceType.CUSTOM
) -> MindscapeTool:
    """
    從函式創建工具(簡化版)

    Args:
        func: 異步函式
        name: 工具名稱
        description: 描述
        source_type: 來源類型

    Returns:
        MindscapeTool 實例

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

    # 從函式簽名推斷參數
    sig = inspect.signature(func)
    parameters = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ['self', 'cls']:
            continue

        param_type = "string"  # 預設類型
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

    # 創建 metadata
    metadata = create_simple_tool_metadata(
        name=name,
        description=description,
        parameters=parameters,
        required=required,
        source_type=source_type
    )

    # 創建動態工具類
    class DynamicTool(MindscapeTool):
        async def execute(self, **kwargs):
            return await func(**kwargs)

    return DynamicTool(metadata)

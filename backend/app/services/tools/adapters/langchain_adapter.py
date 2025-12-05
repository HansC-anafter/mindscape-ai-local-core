"""
LangChain 工具適配器

提供 LangChain 工具與 Mindscape AI 之間的雙向轉換：
1. LangChain Tool → MindscapeTool (from_langchain)
2. MindscapeTool → LangChain Tool (to_langchain)

設計原則：
- 保留工具原始行為
- 自動轉換 schema（支援 Pydantic v1/v2）
- 支援同步和異步執行
- 優雅的錯誤處理和降級
"""
from typing import Dict, Any, Optional, Type, List
import asyncio
import inspect

try:
    from langchain.tools import BaseTool, StructuredTool
    from langchain_core.tools import BaseTool as CoreBaseTool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    BaseTool = None
    CoreBaseTool = None
    StructuredTool = None
    LANGCHAIN_AVAILABLE = False

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolCategory,
    ToolSourceType,
    ToolDangerLevel,
    create_simple_tool_metadata
)


class LangChainToolAdapter(MindscapeTool):
    """
    將 LangChain BaseTool 包裝為 MindscapeTool

    Example:
        >>> from langchain_community.tools import WikipediaQueryRun
        >>> wiki = WikipediaQueryRun()
        >>> mindscape_tool = LangChainToolAdapter(wiki)
        >>> result = await mindscape_tool.execute({"query": "Python"})
    """

    def __init__(self, langchain_tool: Any):
        """
        初始化 LangChain 工具適配器

        Args:
            langchain_tool: LangChain BaseTool 實例

        Raises:
            ImportError: 如果 LangChain 未安裝
            ValueError: 如果不是有效的 LangChain 工具
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is not installed. "
                "Install with: pip install 'langchain>=0.1.0' 'langchain-core>=0.1.0'"
            )

        if not isinstance(langchain_tool, (BaseTool, CoreBaseTool)):
            raise ValueError(
                f"Expected LangChain BaseTool, got {type(langchain_tool)}"
            )

        self.langchain_tool = langchain_tool

        # Extract metadata from LangChain tool
        metadata = self._extract_metadata_from_langchain(langchain_tool)

        super().__init__(metadata)

    def _extract_metadata_from_langchain(self, lc_tool: Any) -> ToolMetadata:
        """
        Extract metadata from LangChain tool

        Args:
            lc_tool: LangChain BaseTool

        Returns:
            ToolMetadata
        """
        # Get basic information
        name = getattr(lc_tool, 'name', 'unknown')
        description = getattr(lc_tool, 'description', '')

        # Extract input schema
        input_schema = self._extract_input_schema(lc_tool)

        # Infer danger level (based on tool name and description)
        danger_level = self._infer_danger_level(name, description)

        # Infer category
        category = self._infer_category(name, description)

        return ToolMetadata(
            name=f"langchain.{name}",
            description=description,
            input_schema=input_schema,
            category=category,
            source_type=ToolSourceType.LANGCHAIN,
            danger_level=danger_level,
            metadata={
                "langchain_tool_class": lc_tool.__class__.__name__,
                "langchain_version": self._get_langchain_version()
            }
        )

    def _extract_input_schema(self, lc_tool: Any) -> Dict[str, Any]:
        """
        提取 LangChain 工具的 input schema

        LangChain 1.0+ 使用 Pydantic v2 的 args_schema
        """
        try:
            # LangChain 1.0+: 使用 args_schema
            if hasattr(lc_tool, 'args_schema') and lc_tool.args_schema:
                # Pydantic v2: model_json_schema()
                if hasattr(lc_tool.args_schema, 'model_json_schema'):
                    schema = lc_tool.args_schema.model_json_schema()
                # Pydantic v1: schema()
                elif hasattr(lc_tool.args_schema, 'schema'):
                    schema = lc_tool.args_schema.schema()
                else:
                    schema = {"type": "object", "properties": {}}

                return schema

            # Fallback: 檢查 args
            elif hasattr(lc_tool, 'args'):
                args = lc_tool.args
                if isinstance(args, dict):
                    return {
                        "type": "object",
                        "properties": args,
                        "required": []
                    }

            # 最後的 fallback: 單個 input 參數
            return {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Tool input"
                    }
                },
                "required": ["input"]
            }

        except Exception as e:
            # 如果提取失敗，使用最簡單的 schema
            return {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": f"Input for {lc_tool.name}"
                    }
                },
                "required": []
            }

    def _infer_danger_level(self, name: str, description: str) -> ToolDangerLevel:
        """
        根據工具名稱和描述推斷危險等級
        """
        danger_keywords = ['delete', 'remove', 'drop', 'execute', 'run', 'shell']
        moderate_keywords = ['write', 'update', 'modify', 'create', 'send']

        name_lower = name.lower()
        desc_lower = description.lower()

        # Check for danger keywords
        if any(kw in name_lower or kw in desc_lower for kw in danger_keywords):
            return ToolDangerLevel.DANGER

        # Check for moderate risk keywords
        if any(kw in name_lower or kw in desc_lower for kw in moderate_keywords):
            return ToolDangerLevel.MODERATE

        # Default: safe
        return ToolDangerLevel.SAFE

    def _infer_category(self, name: str, description: str) -> ToolCategory:
        """
        Infer category based on tool name and description
        """
        category_keywords = {
            ToolCategory.SEARCH: ['search', 'query', 'find', 'lookup', 'wikipedia', 'google'],
            ToolCategory.CONTENT: ['write', 'generate', 'create', 'blog', 'article'],
            ToolCategory.DATA: ['database', 'sql', 'data', 'csv', 'json'],
            ToolCategory.INTEGRATION: ['api', 'slack', 'github', 'jira', 'webhook'],
            ToolCategory.AUTOMATION: ['run', 'execute', 'automate', 'script'],
        }

        name_lower = name.lower()
        desc_lower = description.lower()

        for category, keywords in category_keywords.items():
            if any(kw in name_lower or kw in desc_lower for kw in keywords):
                return category

        return ToolCategory.OTHER

    def _get_langchain_version(self) -> str:
        """獲取 LangChain 版本"""
        try:
            import langchain
            return langchain.__version__
        except:
            return "unknown"

    async def execute(self, input_data: Dict[str, Any]) -> Any:
        """
        執行 LangChain 工具

        Args:
            input_data: 輸入數據

        Returns:
            Tool execution result
        """
        # LangChain tools may be sync or async
        if hasattr(self.langchain_tool, 'ainvoke'):
            # Async execution
            result = await self.langchain_tool.ainvoke(input_data)
        elif hasattr(self.langchain_tool, '_arun'):
            # Legacy async interface
            result = await self.langchain_tool._arun(**input_data)
        elif hasattr(self.langchain_tool, 'invoke'):
            # Sync execution, run in executor
            result = await asyncio.to_thread(
                self.langchain_tool.invoke,
                input_data
            )
        elif hasattr(self.langchain_tool, '_run'):
            # Legacy sync interface
            result = await asyncio.to_thread(
                self.langchain_tool._run,
                **input_data
            )
        else:
            raise NotImplementedError(
                f"Cannot determine how to execute {self.langchain_tool.name}"
            )

        return result


class MindscapeToLangChainAdapter:
    """
    將 MindscapeTool 轉換為 LangChain StructuredTool

    Example:
        >>> mindscape_tool = WordPressListPostsTool(connection)
        >>> langchain_tool = MindscapeToLangChainAdapter.convert(mindscape_tool)
        >>> result = await langchain_tool.ainvoke({"per_page": 10})
    """

    @staticmethod
    def convert(mindscape_tool: MindscapeTool) -> Any:
        """
        轉換 MindscapeTool 為 LangChain Tool

        Args:
            mindscape_tool: MindscapeTool 實例

        Returns:
            LangChain StructuredTool

        Raises:
            ImportError: 如果 LangChain 未安裝
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is not installed. "
                "Install with: pip install 'langchain>=0.1.0'"
            )

        # 創建執行函數
        async def execute_func(**kwargs) -> Any:
            """執行 Mindscape 工具"""
            result = await mindscape_tool.safe_execute(kwargs)
            if result.success:
                return result.result
            else:
                raise Exception(result.error)

        # 從 Mindscape schema 轉換為 Pydantic model
        from pydantic import BaseModel, Field, create_model

        # 構建 Pydantic 欄位
        fields = {}
        schema = mindscape_tool.metadata.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for field_name, field_info in properties.items():
            field_type = MindscapeToLangChainAdapter._json_type_to_python(
                field_info.get("type", "string")
            )
            field_description = field_info.get("description", "")
            field_default = field_info.get("default", ...)

            # 如果是必填且無默認值
            if field_name in required and field_default == ...:
                fields[field_name] = (field_type, Field(description=field_description))
            else:
                fields[field_name] = (
                    field_type,
                    Field(default=field_default, description=field_description)
                )

        # 創建 Pydantic model
        InputModel = create_model(
            f"{mindscape_tool.name.replace('.', '_')}_Input",
            **fields
        )

        # 創建 LangChain StructuredTool
        tool = StructuredTool(
            name=mindscape_tool.name.replace(".", "_"),
            description=mindscape_tool.description,
            args_schema=InputModel,
            coroutine=execute_func
        )

        return tool

    @staticmethod
    def _json_type_to_python(json_type: str) -> Type:
        """將 JSON Schema 類型轉換為 Python 類型"""
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        return type_map.get(json_type, str)


# ============================================
# Convenience functions
# ============================================

def from_langchain(langchain_tool: Any) -> MindscapeTool:
    """
    將 LangChain 工具轉換為 MindscapeTool

    Args:
        langchain_tool: LangChain BaseTool 實例

    Returns:
        MindscapeTool

    Example:
        >>> from langchain_community.tools import WikipediaQueryRun
        >>> wiki = WikipediaQueryRun()
        >>> mindscape_tool = from_langchain(wiki)
        >>> result = await mindscape_tool.execute({"query": "Python"})
    """
    return LangChainToolAdapter(langchain_tool)


def to_langchain(mindscape_tool: MindscapeTool) -> Any:
    """
    將 MindscapeTool 轉換為 LangChain StructuredTool

    Args:
        mindscape_tool: MindscapeTool 實例

    Returns:
        LangChain StructuredTool

    Example:
        >>> from app.services.tools.wordpress.wordpress_tools_v2 import WordPressListPostsTool
        >>> wp_tool = WordPressListPostsTool(connection)
        >>> lc_tool = to_langchain(wp_tool)
        >>> result = await lc_tool.ainvoke({"per_page": 10})
    """
    return MindscapeToLangChainAdapter.convert(mindscape_tool)


def is_langchain_available() -> bool:
    """檢查 LangChain 是否可用"""
    return LANGCHAIN_AVAILABLE


def get_langchain_version() -> Optional[str]:
    """獲取 LangChain 版本"""
    if not LANGCHAIN_AVAILABLE:
        return None
    try:
        import langchain
        return langchain.__version__
    except:
        return "unknown"




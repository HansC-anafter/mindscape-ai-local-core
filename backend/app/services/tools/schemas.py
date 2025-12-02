"""
工具 Schema 定義

定義 Mindscape AI 工具系統的標準化 schema，包括：
- 工具元數據（名稱、描述、schema、分類）
- JSON Schema 兼容的輸入規範
- 工具分類和風險等級枚舉

設計原則：
- 框架中立：不綁定特定工具生態
- JSON Schema 兼容：支援 LangChain/MCP 轉換
- 使用 Pydantic v2 API
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Literal
from enum import Enum


class ToolInputSchema(BaseModel):
    """
    工具輸入參數 schema（對齊 JSON Schema）

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
        default_factory=dict,
        description="Parameter definitions"
    )
    required: List[str] = Field(
        default_factory=list,
        description="Required parameter names"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    }
                },
                "required": ["query"]
            }
        }


class ToolSourceType(str, Enum):
    """工具來源類型"""
    BUILTIN = "builtin"      # 內建工具（WordPress, Notion, etc.）
    LANGCHAIN = "langchain"  # LangChain 社群工具
    MCP = "mcp"              # MCP 協議工具
    CUSTOM = "custom"        # 自定義工具


class ToolCategory(str, Enum):
    """工具分類"""
    CONTENT = "content"            # 內容創作/管理
    DATA = "data"                  # 資料查詢/搜尋
    AUTOMATION = "automation"      # 自動化/腳本
    COMMUNICATION = "communication" # 通訊/通知
    ANALYSIS = "analysis"          # 分析/計算


class ToolDangerLevel(str, Enum):
    """工具風險等級"""
    LOW = "low"          # 只讀操作
    MEDIUM = "medium"    # 寫入操作
    HIGH = "high"        # 修改/刪除操作
    CRITICAL = "critical" # 執行/系統操作


class ToolMetadata(BaseModel):
    """
    工具元數據（對齊 LangChain BaseTool）

    這個 schema 可以與 LangChain BaseTool 雙向轉換，同時也能映射到 MCP tool spec。

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
    # 核心欄位（對齊 LangChain BaseTool）
    name: str = Field(
        ...,
        description="工具名稱（唯一識別碼，建議使用 snake_case）",
        pattern=r"^[a-z][a-z0-9_]*$"
    )
    description: str = Field(
        ...,
        description="工具功能描述（會被 LLM 讀取，需清晰說明功能）",
        min_length=10,
        max_length=500
    )
    input_schema: ToolInputSchema = Field(
        ...,
        description="輸入參數的 JSON Schema"
    )
    return_direct: bool = Field(
        default=False,
        description="是否直接返回結果給用戶（不經過 LLM 處理）"
    )

    # Mindscape 擴展欄位
    category: ToolCategory = Field(
        default=ToolCategory.AUTOMATION,
        description="工具分類"
    )
    source_type: ToolSourceType = Field(
        ...,
        description="工具來源類型"
    )
    provider: Optional[str] = Field(
        default=None,
        description="工具提供者（如 'wordpress', 'github', 'wikipedia'）"
    )
    danger_level: ToolDangerLevel = Field(
        default=ToolDangerLevel.LOW,
        description="風險等級"
    )

    # 可選欄位
    version: Optional[str] = Field(
        default="1.0.0",
        description="工具版本"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="標籤（用於搜尋和分類）"
    )
    examples: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="使用範例"
    )

    # MCP 相關（預留）
    mcp_server_id: Optional[str] = Field(
        default=None,
        description="MCP server ID（如果是 MCP 工具）"
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
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                },
                "category": "data",
                "source_type": "langchain",
                "provider": "wikipedia",
                "danger_level": "low",
                "return_direct": False
            }
        }

    def to_langchain_schema(self) -> Dict[str, Any]:
        """
        轉換成 LangChain tool schema

        Returns:
            LangChain 可以使用的 schema dict
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_dump(),
            "return_direct": self.return_direct
        }

    def to_mcp_schema(self) -> Dict[str, Any]:
        """
        轉換成 MCP tool schema

        Returns:
            MCP 協議的 tool info
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema.model_dump()
        }

    def is_dangerous(self) -> bool:
        """判斷是否為危險操作"""
        return self.danger_level in [ToolDangerLevel.HIGH, ToolDangerLevel.CRITICAL]

    def requires_confirmation(self) -> bool:
        """判斷是否需要用戶確認"""
        return self.danger_level in [ToolDangerLevel.MEDIUM, ToolDangerLevel.HIGH, ToolDangerLevel.CRITICAL]


class ToolExecutionResult(BaseModel):
    """工具執行結果"""
    success: bool = Field(..., description="是否執行成功")
    result: Any = Field(default=None, description="執行結果")
    error: Optional[str] = Field(default=None, description="錯誤訊息")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="額外的元數據（執行時間、token 使用量等）"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "result": "Wikipedia summary of...",
                "error": None,
                "metadata": {
                    "execution_time_ms": 250,
                    "source": "wikipedia"
                }
            }
        }


# 便捷函式
def create_simple_tool_metadata(
    name: str,
    description: str,
    parameters: Dict[str, Dict[str, Any]],
    required: List[str] = None,
    source_type: ToolSourceType = ToolSourceType.BUILTIN,
    **kwargs
) -> ToolMetadata:
    """
    快速創建簡單的工具 metadata

    Args:
        name: 工具名稱
        description: 描述
        parameters: 參數定義 {"param_name": {"type": "string", "description": "..."}}
        required: 必填參數列表
        source_type: 來源類型
        **kwargs: 其他 ToolMetadata 欄位

    Returns:
        ToolMetadata 實例

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
        type="object",
        properties=parameters,
        required=required or []
    )

    return ToolMetadata(
        name=name,
        description=description,
        input_schema=input_schema,
        source_type=source_type,
        **kwargs
    )

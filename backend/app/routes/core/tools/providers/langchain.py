"""
LangChain tool provider routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.app.services.tool_registry import ToolRegistryService
from ..base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class LangChainRegisterRequest(BaseModel):
    """Register LangChain tool request"""
    tool_name: str = Field(..., description="LangChain tool name")
    config: Dict[str, Any] = Field(default_factory=dict, description="Tool configuration (e.g., API keys)")
    profile_id: Optional[str] = Field(default='default-user', description="User ID")


class LangChainDiscoverRequest(BaseModel):
    """Batch discover LangChain tools request"""
    tool_names: List[str] = Field(..., description="List of tool names to discover")
    profile_id: Optional[str] = Field(default='default-user', description="User ID")


@router.get("/langchain/available", response_model=Dict[str, Any])
async def get_available_langchain_tools():
    """
    Get all available LangChain tools list

    Used by Config Assistant to query tools that can be recommended to users
    """
    try:
        from backend.app.services.tools.providers.langchain_known_tools import KNOWN_LANGCHAIN_TOOLS

        return {
            "success": True,
            "tools": KNOWN_LANGCHAIN_TOOLS,
            "count": len(KNOWN_LANGCHAIN_TOOLS)
        }
    except ImportError:
        return {
            "success": True,
            "tools": [
                {
                    "name": "wikipedia",
                    "display_name": "Wikipedia",
                    "description": "Search Wikipedia",
                    "requires_api_key": False,
                    "category": "search"
                }
            ],
            "count": 1,
            "note": "Full tool list requires langchain-community installation"
        }


@router.post("/langchain/register", response_model=Dict[str, Any])
async def register_langchain_tool(
    request: LangChainRegisterRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Register single LangChain tool (convenience endpoint)

    Used by Config Assistant for automatic tool configuration
    """
    try:
        from backend.app.services.tools.adapters.langchain_adapter import from_langchain
        from backend.app.services.tools.providers.langchain_known_tools import get_langchain_tool_class

        tool_class_info = get_langchain_tool_class(request.tool_name)
        if not tool_class_info:
            raise_api_error(404, f"Unknown LangChain tool: {request.tool_name}")

        module_path = tool_class_info["module"]
        class_name = tool_class_info["class"]

        module = __import__(module_path, fromlist=[class_name])
        tool_class = getattr(module, class_name)

        if request.config:
            lc_tool = tool_class(**request.config)
        else:
            lc_tool = tool_class()

        mindscape_tool = from_langchain(lc_tool)

        return {
            "success": True,
            "tool_name": request.tool_name,
            "tool_id": f"langchain.{request.tool_name}",
            "message": f"LangChain tool {request.tool_name} registered successfully"
        }

    except ImportError as e:
        raise_api_error(500, f"Failed to import LangChain tool: {str(e)}")
    except Exception as e:
        raise_api_error(500, f"Registration failed: {str(e)}")


@router.post("/langchain/discover", response_model=Dict[str, Any])
async def discover_langchain_tools(
    request: LangChainDiscoverRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Batch discover and register LangChain tools

    Used by Config Assistant to configure multiple tools at once
    """
    try:
        from backend.app.services.tools.adapters.langchain_adapter import from_langchain
        from backend.app.services.tools.providers.langchain_known_tools import get_langchain_tool_class

        results = {
            "success": True,
            "discovered": [],
            "failed": []
        }

        for tool_name in request.tool_names:
            try:
                tool_class_info = get_langchain_tool_class(tool_name)
                if not tool_class_info:
                    results["failed"].append({
                        "tool_name": tool_name,
                        "error": "Unknown tool"
                    })
                    continue

                module_path = tool_class_info["module"]
                class_name = tool_class_info["class"]

                module = __import__(module_path, fromlist=[class_name])
                tool_class = getattr(module, class_name)

                lc_tool = tool_class()

                mindscape_tool = from_langchain(lc_tool)

                results["discovered"].append({
                    "tool_name": tool_name,
                    "tool_id": f"langchain.{tool_name}",
                    "description": tool_class_info.get("description", "")
                })

            except Exception as e:
                results["failed"].append({
                    "tool_name": tool_name,
                    "error": str(e)
                })

        return results

    except Exception as e:
        raise_api_error(500, str(e))


@router.get("/langchain/status", response_model=Dict[str, Any])
async def get_langchain_tools_status(
    profile_id: str = Query('default-user', description="User ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get registered LangChain tools status

    Used by Config Assistant to check which tools are installed
    """
    try:
        all_tools = registry.get_tools()
        langchain_tools = [
            tool for tool in all_tools
            if tool.provider == "langchain" or tool.tool_id.startswith("langchain.")
        ]

        return {
            "success": True,
            "installed": [tool.tool_id for tool in langchain_tools],
            "count": len(langchain_tools),
            "tools": [
                {
                    "tool_id": tool.tool_id,
                    "display_name": tool.display_name,
                    "description": tool.description,
                    "enabled": tool.enabled
                }
                for tool in langchain_tools
            ]
        }
    except Exception as e:
        raise_api_error(500, str(e))


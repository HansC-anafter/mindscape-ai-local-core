"""
Playbook tool dependency checking and installation
"""

import logging
import os
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query

from ....services.tool_status_checker import ToolStatusChecker
from ....services.tool_registry import ToolRegistryService
from ....services.playbook_tool_checker import PlaybookToolChecker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbooks-tools"])


@router.get("/{playbook_code}/tools/check", response_model=Dict[str, Any])
async def check_playbook_tools(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="User profile ID")
):
    """
    Check playbook tool dependencies and availability

    Returns:
        {
            "playbook_code": "...",
            "tools": {
                "available": [...],
                "missing": [...],
                "can_auto_install": [...]
            }
        }
    """
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        playbook = await playbook_service.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        from ....services.playbook_tool_resolver import ToolDependencyResolver

        resolver = ToolDependencyResolver()
        result = await resolver.resolve_dependencies(
            playbook.metadata.tool_dependencies
        )

        return {
            "playbook_code": playbook_code,
            "tools": {
                "available": result["available"],
                "missing": result["missing"],
                "can_auto_install": result["can_auto_install"],
                "errors": result["errors"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking playbook tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_code}/tools/install", response_model=Dict[str, Any])
async def install_playbook_tools(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="User profile ID")
):
    """
    Auto-install tools required by Playbook

    Returns:
        {
            "success": bool,
            "installed": [...],
            "failed": [...],
            "message": "..."
        }
    """
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        playbook = await playbook_service.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        from ....services.playbook_tool_resolver import ToolDependencyResolver

        resolver = ToolDependencyResolver()
        check_result = await resolver.resolve_dependencies(
            playbook.metadata.tool_dependencies
        )

        if not check_result["missing"]:
            return {
                "success": True,
                "installed": [],
                "failed": [],
                "available": check_result["available"],
                "message": "All tools are already available"
            }

        installed = []
        failed = []

        for tool_dep in playbook.metadata.tool_dependencies:
            can_install = any(
                t["name"] == tool_dep.name
                for t in check_result["can_auto_install"]
            )

            if can_install:
                try:
                    install_result = await resolver.auto_install_tool(tool_dep)
                    if install_result["success"]:
                        installed.append({
                            "name": tool_dep.name,
                            "type": tool_dep.type
                        })
                        logger.info(f"Successfully installed tool: {tool_dep.name}")
                    else:
                        failed.append({
                            "name": tool_dep.name,
                            "type": tool_dep.type,
                            "error": install_result["error"]
                        })
                        logger.error(f"Failed to install tool {tool_dep.name}: {install_result['error']}")
                except Exception as e:
                    failed.append({
                        "name": tool_dep.name,
                        "type": tool_dep.type,
                        "error": str(e)
                    })
                    logger.error(f"Exception installing tool {tool_dep.name}: {e}")

        still_missing = [
            t for t in check_result["missing"]
            if t["required"] and t["name"] not in [i["name"] for i in installed]
        ]

        if still_missing:
            return {
                "success": False,
                "installed": installed,
                "failed": failed,
                "still_missing": still_missing,
                "message": "部分必要工具無法安裝"
            }

        return {
            "success": True,
            "installed": installed,
            "failed": failed,
            "available": check_result["available"],
            "message": f"成功安裝 {len(installed)} 個工具"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error installing playbook tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_code}/tools-check", response_model=Dict[str, Any])
async def check_playbook_tools_readiness(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="Profile ID")
):
    """
    Check playbook tool dependencies and readiness

    Returns readiness status based on tool connection status:
    - ready: All required tools are connected
    - needs_setup: One or more required tools are registered_but_not_connected
    - unsupported: One or more required tools are unavailable

    Example:
        GET /api/v1/playbooks/content_drafting/tools-check?profile_id=user123
    """
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store), mindscape_store

        playbook = await playbook_service.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook_code}")

        data_dir = os.getenv("DATA_DIR", "./data")
        tool_registry = ToolRegistryService(data_dir=data_dir)
        tool_status_checker = ToolStatusChecker(tool_registry)
        playbook_tool_checker = PlaybookToolChecker(tool_status_checker)

        readiness, tool_statuses, missing_required = playbook_tool_checker.check_playbook_tools(
            playbook=playbook,
            profile_id=profile_id
        )

        required_tools = playbook_tool_checker._extract_required_tools(playbook.metadata)

        return {
            "playbook_code": playbook_code,
            "readiness_status": readiness.value,
            "tool_statuses": {
                tool_type: status.value
                for tool_type, status in tool_statuses.items()
            },
            "missing_required_tools": missing_required,
            "required_tools": required_tools,
            "optional_tools": playbook.metadata.optional_tools
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking playbook tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

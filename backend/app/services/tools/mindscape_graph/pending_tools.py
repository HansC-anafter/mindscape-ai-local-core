"""
Pending Changes Tools - 審計機制

提供 LLM 和使用者管理待審核變更的工具。
"""

import logging
from typing import Dict, Any, List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolInputSchema,
    ToolCategory,
)

logger = logging.getLogger(__name__)


class PendingChangesListTool(MindscapeTool):
    """列出待審核的圖變更"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.pending_list",
            description="列出 mindscape 圖中待審核的變更",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "actor_filter": {
                        "type": "string",
                        "description": "按來源篩選：llm, user, system, playbook",
                        "enum": ["llm", "user", "system", "playbook"],
                    },
                },
                required=["workspace_id"],
            ),
            category=ToolCategory.DATA,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        actor_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出待審核變更"""
        try:
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            changelog_store = GraphChangelogStore()
            pending_changes = changelog_store.get_pending_changes(
                workspace_id=workspace_id,
                actor=actor_filter,
            )

            return {
                "success": True,
                "workspace_id": workspace_id,
                "total_pending": len(pending_changes),
                "changes": [c.to_dict() for c in pending_changes],
            }
        except Exception as e:
            logger.error(f"Failed to list pending changes: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


class PendingChangesApproveTool(MindscapeTool):
    """批准或拒絕待審核的圖變更"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.pending_approve",
            description="批准或拒絕待審核的 mindscape 圖變更",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "change_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要處理的待審核變更 ID 列表",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["approve", "reject"],
                        "description": "操作類型：approve（批准）或 reject（拒絕）",
                    },
                    "profile_id": {
                        "type": "string",
                        "description": "執行操作的使用者 Profile ID",
                    },
                },
                required=["change_ids", "action", "profile_id"],
            ),
            category=ToolCategory.WRITE,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="medium",
        )
        super().__init__(metadata)

    async def execute(
        self,
        change_ids: List[str],
        action: str,
        profile_id: str,
    ) -> Dict[str, Any]:
        """處理待審核變更"""
        try:
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            if not change_ids:
                return {"success": False, "error": "No change IDs provided"}

            if action not in ["approve", "reject"]:
                return {"success": False, "error": f"Invalid action: {action}"}

            changelog_store = GraphChangelogStore()
            results = []
            success_count = 0
            error_count = 0

            for change_id in change_ids:
                if action == "approve":
                    result = changelog_store.apply_change(
                        change_id=change_id,
                        applied_by=profile_id,
                    )
                else:  # reject
                    result = changelog_store.reject_change(change_id)

                results.append(
                    {
                        "change_id": change_id,
                        "action": action,
                        "success": result.get("success", False),
                        "error": result.get("error"),
                    }
                )

                if result.get("success"):
                    success_count += 1
                else:
                    error_count += 1

            return {
                "success": error_count == 0,
                "processed": len(change_ids),
                "success_count": success_count,
                "error_count": error_count,
                "results": results,
            }
        except Exception as e:
            logger.error(f"Failed to process pending changes: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


class UndoChangeTool(MindscapeTool):
    """撤銷已應用的圖變更"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.undo",
            description="撤銷已應用的 mindscape 圖變更，恢復到變更前的狀態",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "change_id": {"type": "string", "description": "要撤銷的變更 ID"},
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID（用於驗證）",
                    },
                },
                required=["change_id"],
            ),
            category=ToolCategory.WRITE,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="medium",
        )
        super().__init__(metadata)

    async def execute(
        self,
        change_id: str,
        workspace_id: str = "",
    ) -> Dict[str, Any]:
        """撤銷變更"""
        try:
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            changelog_store = GraphChangelogStore()
            result = changelog_store.undo_change(change_id)

            if result.get("success"):
                return {
                    "success": True,
                    "change_id": change_id,
                    "message": "變更已成功撤銷",
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                }
        except Exception as e:
            logger.error(f"Failed to undo change: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


class GraphHistoryTool(MindscapeTool):
    """查看圖變更歷史"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.history",
            description="查看 mindscape 圖的變更歷史，支援時間回溯",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "返回的最大條目數",
                    },
                    "include_pending": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否包含待審核的變更",
                    },
                },
                required=["workspace_id"],
            ),
            category=ToolCategory.DATA,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        limit: int = 20,
        include_pending: bool = False,
    ) -> Dict[str, Any]:
        """查看變更歷史"""
        try:
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            changelog_store = GraphChangelogStore()
            history = changelog_store.get_history(
                workspace_id=workspace_id,
                limit=limit,
                include_pending=include_pending,
            )
            current_version = changelog_store.get_current_version(workspace_id)

            return {
                "success": True,
                "workspace_id": workspace_id,
                "current_version": current_version,
                "total_entries": len(history),
                "history": [entry.to_dict() for entry in history],
            }
        except Exception as e:
            logger.error(f"Failed to get history: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

"""
Graph Node/Edge Tools - 細節處理

提供 LLM 對單一節點/邊的 CRUD 操作。
所有操作會記錄到 changelog 並可選擇性地進入待審核狀態。
"""

import logging
import uuid
from typing import Dict, Any, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolInputSchema,
    ToolCategory,
)

logger = logging.getLogger(__name__)


class NodeCreateTool(MindscapeTool):
    """建立 mindscape 節點"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.create_node",
            description="在 mindscape 圖中建立新節點。預設會進入待審核狀態。",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "type": {
                        "type": "string",
                        "description": "節點類型：intent, note, milestone, playbook, execution, artifact",
                        "enum": [
                            "intent",
                            "note",
                            "milestone",
                            "playbook",
                            "execution",
                            "artifact",
                        ],
                    },
                    "label": {"type": "string", "description": "節點標籤"},
                    "position_x": {
                        "type": "number",
                        "default": 0,
                        "description": "X 座標",
                    },
                    "position_y": {
                        "type": "number",
                        "default": 0,
                        "description": "Y 座標",
                    },
                    "metadata": {"type": "object", "description": "附加元資料"},
                    "auto_apply": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否跳過審核直接應用",
                    },
                },
                required=["workspace_id", "type", "label"],
            ),
            category=ToolCategory.WRITE,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        type: str,
        label: str,
        position_x: float = 0,
        position_y: float = 0,
        metadata: Optional[Dict[str, Any]] = None,
        auto_apply: bool = False,
        profile_id: str = "",
    ) -> Dict[str, Any]:
        """建立節點"""
        try:
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            node_id = f"manual:{uuid.uuid4()}"
            changelog_store = GraphChangelogStore()

            after_state = {
                "id": node_id,
                "type": type,
                "label": label,
                "position": {"x": position_x, "y": position_y},
                "metadata": metadata or {},
                "status": "manual",
            }

            change_id = changelog_store.create_pending_change(
                workspace_id=workspace_id,
                operation="create_node",
                target_type="node",
                target_id=node_id,
                after_state=after_state,
                actor="llm" if not profile_id else "user",
                actor_context="",
            )

            if auto_apply and profile_id:
                result = changelog_store.apply_change(change_id, applied_by=profile_id)
                if not result.get("success"):
                    return {
                        "success": False,
                        "error": result.get("error", "Failed to apply change"),
                    }

            return {
                "success": True,
                "node_id": node_id,
                "change_id": change_id,
                "message": f"節點 '{label}' {'建立成功' if auto_apply else '已加入待審核清單'}",
                "requires_approval": not auto_apply,
            }
        except Exception as e:
            logger.error(f"Failed to create node: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


class NodeUpdateTool(MindscapeTool):
    """更新 mindscape 節點"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.update_node",
            description="更新 mindscape 節點的屬性（標籤、位置）",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "node_id": {"type": "string", "description": "節點 ID"},
                    "label": {"type": "string", "description": "新標籤"},
                    "position_x": {"type": "number", "description": "新 X 座標"},
                    "position_y": {"type": "number", "description": "新 Y 座標"},
                    "auto_apply": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否跳過審核直接應用",
                    },
                },
                required=["workspace_id", "node_id"],
            ),
            category=ToolCategory.WRITE,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        node_id: str,
        label: Optional[str] = None,
        position_x: Optional[float] = None,
        position_y: Optional[float] = None,
        auto_apply: bool = False,
        profile_id: str = "",
    ) -> Dict[str, Any]:
        """更新節點"""
        try:
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )
            from backend.app.services.mindscape_graph_service import (
                MindscapeGraphService,
            )
            from backend.app.services.mindscape_store import MindscapeStore

            # 獲取當前節點狀態作為 before_state
            store = MindscapeStore()
            service = MindscapeGraphService(db_path=store.db_path)
            graph = await service.get_graph(workspace_id=workspace_id)

            current_node = None
            for node in graph.nodes:
                if node.id == node_id:
                    current_node = node
                    break

            before_state = None
            if current_node:
                before_state = {
                    "id": current_node.id,
                    "label": current_node.label,
                    "position": graph.overlay.node_positions.get(
                        node_id, {"x": 0, "y": 0}
                    ),
                }

            after_state: Dict[str, Any] = {}
            if label is not None:
                after_state["label"] = label
            if position_x is not None or position_y is not None:
                position = {"x": position_x or 0, "y": position_y or 0}
                after_state["position"] = position

            if not after_state:
                return {"success": False, "error": "No updates provided"}

            changelog_store = GraphChangelogStore()
            change_id = changelog_store.create_pending_change(
                workspace_id=workspace_id,
                operation="update_node",
                target_type="node",
                target_id=node_id,
                after_state=after_state,
                before_state=before_state,
                actor="llm" if not profile_id else "user",
            )

            if auto_apply and profile_id:
                result = changelog_store.apply_change(change_id, applied_by=profile_id)
                if not result.get("success"):
                    return {"success": False, "error": result.get("error")}

            return {
                "success": True,
                "node_id": node_id,
                "change_id": change_id,
                "message": f"節點 '{node_id}' {'更新成功' if auto_apply else '更新已加入待審核清單'}",
                "requires_approval": not auto_apply,
            }
        except Exception as e:
            logger.error(f"Failed to update node: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


class EdgeCreateTool(MindscapeTool):
    """建立 mindscape 邊"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.create_edge",
            description="在 mindscape 圖中建立節點間的連接",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "from_id": {"type": "string", "description": "起始節點 ID"},
                    "to_id": {"type": "string", "description": "目標節點 ID"},
                    "edge_type": {
                        "type": "string",
                        "default": "related_to",
                        "description": "邊類型",
                        "enum": [
                            "depends_on",
                            "related_to",
                            "derived_from",
                            "triggers",
                            "produces",
                        ],
                    },
                    "auto_apply": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否跳過審核直接應用",
                    },
                },
                required=["workspace_id", "from_id", "to_id"],
            ),
            category=ToolCategory.WRITE,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        from_id: str,
        to_id: str,
        edge_type: str = "related_to",
        auto_apply: bool = False,
        profile_id: str = "",
    ) -> Dict[str, Any]:
        """建立邊"""
        try:
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            edge_id = f"edge:{from_id[:8]}-{to_id[:8]}-{edge_type}"

            after_state = {
                "id": edge_id,
                "from_id": from_id,
                "to_id": to_id,
                "type": edge_type,
                "origin": "user",
                "confidence": 1.0,
                "status": "manual",
            }

            changelog_store = GraphChangelogStore()
            change_id = changelog_store.create_pending_change(
                workspace_id=workspace_id,
                operation="create_edge",
                target_type="edge",
                target_id=edge_id,
                after_state=after_state,
                actor="llm" if not profile_id else "user",
            )

            if auto_apply and profile_id:
                result = changelog_store.apply_change(change_id, applied_by=profile_id)
                if not result.get("success"):
                    return {"success": False, "error": result.get("error")}

            return {
                "success": True,
                "edge_id": edge_id,
                "change_id": change_id,
                "message": f"邊 {from_id} → {to_id} {'建立成功' if auto_apply else '已加入待審核清單'}",
                "requires_approval": not auto_apply,
            }
        except Exception as e:
            logger.error(f"Failed to create edge: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

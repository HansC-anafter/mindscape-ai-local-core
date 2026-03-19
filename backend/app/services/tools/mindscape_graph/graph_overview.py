"""
Graph Overview Tools - 全局把控

提供 LLM 對整個 mindscape 圖的高層理解，
不需要逐一查看每個節點。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolInputSchema,
    ToolCategory,
)

logger = logging.getLogger(__name__)


class GraphOverviewTool(MindscapeTool):
    """取得 mindscape 圖的全局摘要"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.overview",
            description="取得 mindscape 圖的摘要，包含節點數量、類型分布、最近活動節點、待審核變更",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "include_recent": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否包含最近活動的節點",
                    },
                    "include_pending": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否包含待審核變更數量",
                    },
                    "max_recent": {
                        "type": "integer",
                        "default": 10,
                        "description": "最近活動節點的數量上限",
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
        include_recent: bool = True,
        include_pending: bool = True,
        max_recent: int = 10,
    ) -> Dict[str, Any]:
        """取得圖摘要"""
        try:
            from backend.app.services.mindscape_graph_service import (
                MindscapeGraphService,
            )
            from backend.app.services.mindscape_store import MindscapeStore
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            store = MindscapeStore()
            service = MindscapeGraphService(db_path=store.db_path)

            graph = await service.get_graph(workspace_id=workspace_id)

            # 統計節點類型
            type_counts: Dict[str, int] = {}
            for node in graph.nodes:
                node_type = node.type
                type_counts[node_type] = type_counts.get(node_type, 0) + 1

            # 統計邊類型
            edge_type_counts: Dict[str, int] = {}
            for edge in graph.edges:
                edge_type = edge.type.value
                edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1

            result: Dict[str, Any] = {
                "workspace_id": workspace_id,
                "total_nodes": len(graph.nodes),
                "total_edges": len(graph.edges),
                "node_types": type_counts,
                "edge_types": edge_type_counts,
                "scope_type": graph.scope_type,
                "derived_at": (
                    graph.derived_at.isoformat() if graph.derived_at else None
                ),
            }

            if include_recent:
                # 取得最近建立/更新的節點
                sorted_nodes = sorted(
                    graph.nodes,
                    key=lambda n: n.created_at or datetime.min,
                    reverse=True,
                )[:max_recent]
                result["recent_nodes"] = [
                    {
                        "id": n.id,
                        "type": n.type,
                        "label": n.label,
                        "status": (
                            n.status.value
                            if hasattr(n.status, "value")
                            else str(n.status)
                        ),
                    }
                    for n in sorted_nodes
                ]

            if include_pending:
                # 取得待審核變更數量
                changelog_store = GraphChangelogStore()
                pending_changes = changelog_store.get_pending_changes(workspace_id)
                result["pending_changes_count"] = len(pending_changes)
                result["pending_changes_summary"] = [
                    {
                        "id": c.id,
                        "operation": c.operation,
                        "target_type": c.target_type,
                        "actor": c.actor,
                    }
                    for c in pending_changes[:5]  # 只顯示前 5 個
                ]

            return result
        except Exception as e:
            logger.error(f"Failed to get graph overview: {e}", exc_info=True)
            return {
                "error": str(e),
                "workspace_id": workspace_id,
            }


class GraphSuggestTool(MindscapeTool):
    """根據對話建議圖結構變更 - 建議會進入待審核狀態"""

    def __init__(self):
        metadata = ToolMetadata(
            name="mindscape_graph.suggest",
            description="根據對話歷史分析，建議 mindscape 圖的結構變更（新增節點、合併、重命名）。建議會進入待審核狀態，需要使用者確認後才會應用。",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "workspace_id": {"type": "string", "description": "Workspace ID"},
                    "conversation_context": {
                        "type": "string",
                        "description": "對話上下文摘要",
                    },
                    "user_intent": {
                        "type": "string",
                        "description": "使用者的意圖描述",
                    },
                    "auto_apply": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否跳過審核直接應用（僅限使用者明確要求）",
                    },
                },
                required=["workspace_id", "conversation_context"],
            ),
            category=ToolCategory.AI,
            source_type="capability",
            provider="mindscape_graph",
            danger_level="medium",
        )
        super().__init__(metadata)

    async def execute(
        self,
        workspace_id: str,
        conversation_context: str,
        user_intent: str = "",
        auto_apply: bool = False,
        profile_id: str = "",
    ) -> Dict[str, Any]:
        """使用 LLM 分析並建議圖結構變更"""
        try:
            from backend.app.capabilities.core_llm.services.structured import (
                extract_structured,
            )
            from backend.app.services.mindscape_graph_service import (
                MindscapeGraphService,
            )
            from backend.app.services.mindscape_store import MindscapeStore
            from backend.app.services.stores.graph_changelog_store import (
                GraphChangelogStore,
            )

            store = MindscapeStore()
            service = MindscapeGraphService(db_path=store.db_path)

            # 取得當前圖結構
            graph = await service.get_graph(workspace_id=workspace_id)

            # 建立圖摘要
            existing_nodes = [
                {"id": n.id, "type": n.type, "label": n.label}
                for n in graph.nodes[:50]  # 限制數量
            ]

            # 使用 LLM 分析
            schema = {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [
                                        "create_node",
                                        "update_node",
                                        "create_edge",
                                    ],
                                },
                                "target_id": {"type": "string"},
                                "label": {"type": "string"},
                                "node_type": {"type": "string"},
                                "from_id": {"type": "string"},
                                "to_id": {"type": "string"},
                                "edge_type": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                            "required": ["action", "reason"],
                        },
                    },
                    "summary": {"type": "string"},
                },
                "required": ["suggestions", "summary"],
            }

            prompt = f"""
分析以下對話上下文和現有 mindscape 節點，建議圖結構變更：

## 對話上下文
{conversation_context}

## 使用者意圖
{user_intent or "未明確指定"}

## 現有節點（前50個）
{existing_nodes}

請建議結構變更：
- create_node: 建立新節點（提供 node_type 和 label）
- update_node: 更新現有節點（提供 target_id 和 label）
- create_edge: 建立邊連接（提供 from_id, to_id, edge_type）

請提供具體、可執行的建議。每個建議都需要說明原因。
"""

            result = await extract_structured(prompt, schema)

            # 將建議寫入 pending changes
            changelog_store = GraphChangelogStore()
            pending_ids = []

            for suggestion in result.get("suggestions", []):
                action = suggestion["action"]
                target_type = "node" if "node" in action else "edge"

                # 構造 target_id
                if action == "create_node":
                    import uuid

                    target_id = f"suggested:{uuid.uuid4()}"
                    after_state = {
                        "id": target_id,
                        "type": suggestion.get("node_type", "note"),
                        "label": suggestion.get("label", "New Node"),
                        "status": "suggested",
                        "metadata": {"reason": suggestion.get("reason", "")},
                    }
                elif action == "update_node":
                    target_id = suggestion.get("target_id", "unknown")
                    after_state = {
                        "label": suggestion.get("label"),
                        "reason": suggestion.get("reason", ""),
                    }
                elif action == "create_edge":
                    target_id = f"edge:{suggestion.get('from_id', 'a')}-{suggestion.get('to_id', 'b')}"
                    after_state = {
                        "id": target_id,
                        "from_id": suggestion.get("from_id"),
                        "to_id": suggestion.get("to_id"),
                        "type": suggestion.get("edge_type", "related_to"),
                        "reason": suggestion.get("reason", ""),
                    }
                else:
                    continue

                change_id = changelog_store.create_pending_change(
                    workspace_id=workspace_id,
                    operation=action,
                    target_type=target_type,
                    target_id=target_id,
                    after_state=after_state,
                    actor="llm",
                    actor_context=f"conversation:{conversation_context[:200]}",
                )
                pending_ids.append(change_id)

                # 如果 auto_apply，直接應用
                if auto_apply and profile_id:
                    changelog_store.apply_change(change_id, applied_by=profile_id)

            return {
                "success": True,
                "pending_change_ids": pending_ids,
                "suggestions": result.get("suggestions", []),
                "summary": result.get("summary", ""),
                "requires_approval": not auto_apply,
                "auto_applied": auto_apply,
            }
        except Exception as e:
            logger.error(f"Failed to generate graph suggestions: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

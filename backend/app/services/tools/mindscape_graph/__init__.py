"""
Mindscape Graph Tools

Tools enabling LLM to interact with the Mindscape Graph.
"""

from .graph_overview import GraphOverviewTool, GraphSuggestTool
from .graph_tools import NodeCreateTool, NodeUpdateTool, EdgeCreateTool
from .pending_tools import (
    PendingChangesListTool,
    PendingChangesApproveTool,
    UndoChangeTool,
    GraphHistoryTool,
)

__all__ = [
    # 全局把控
    "GraphOverviewTool",
    "GraphSuggestTool",
    # 細節處理
    "NodeCreateTool",
    "NodeUpdateTool",
    "EdgeCreateTool",
    # 審計機制
    "PendingChangesListTool",
    "PendingChangesApproveTool",
    "UndoChangeTool",
    "GraphHistoryTool",
]


def get_all_tools():
    """Get all mindscape graph tools"""
    return [
        GraphOverviewTool(),
        GraphSuggestTool(),
        NodeCreateTool(),
        NodeUpdateTool(),
        EdgeCreateTool(),
        PendingChangesListTool(),
        PendingChangesApproveTool(),
        UndoChangeTool(),
        GraphHistoryTool(),
    ]

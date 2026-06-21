"""Task projection helpers for meeting execution graphs."""

from __future__ import annotations

from typing import List

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
)
from backend.app.models.workspace import Task
from backend.app.services.meeting_graph.task_projection_core import (
    build_object_action_nodes,
    build_planner_contract_tool_nodes,
    build_planner_tool_plan_nodes,
    planner_binding_from_task,
    planner_tool_plan_from_task,
)


def build_task_graph_nodes(
    task: Task,
) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    planner_binding = planner_binding_from_task(task)
    if task.task_type == "tool_execution" and planner_binding:
        return build_planner_contract_tool_nodes(task, planner_binding)

    planner_tool_plan = planner_tool_plan_from_task(task)
    if task.task_type == "tool_execution" and planner_tool_plan:
        return build_planner_tool_plan_nodes(task, planner_tool_plan)

    return build_object_action_nodes(task)

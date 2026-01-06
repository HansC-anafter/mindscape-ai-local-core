"""
Dashboard data mapping constants
Defines complete field mapping from Local-Core tables to Dashboard DTOs
"""

from typing import Dict, Any, Optional
from datetime import datetime


# ==================== Status Mappings ====================

# Playbook Execution Status -> Case Status
EXECUTION_TO_CASE_STATUS: Dict[str, str] = {
    "running": "open",
    "paused": "blocked",
    "done": "completed",
    "failed": "blocked",
    "cancelled": "cancelled",
}

# Task Status -> Assignment Status
TASK_TO_ASSIGNMENT_STATUS: Dict[str, str] = {
    "pending": "pending",
    "running": "in_progress",
    "succeeded": "completed",
    "failed": "failed",
    "cancelled_by_user": "cancelled",
    "expired": "cancelled",
}

# Inbox priority tier mapping (from site-hub specification)
INBOX_PRIORITY_TIER: Dict[str, int] = {
    "needs_changes": 0,
    "pending_decision": 1,
    "assignment": 2,
    "mention": 3,
    "delegated_pending": 4,
    "system_alert": 5,
    "case_update": 6,
}


# ==================== Field Mappings ====================

def map_execution_to_case(
    execution: Dict[str, Any],
    workspace_id: str,
    workspace_name: str,
    owner_user_id: str,
    tasks_count: int = 0
) -> Dict[str, Any]:
    """
    Playbook Execution -> CaseCardDTO complete field mapping

    Explicitly defines source for each field
    """
    metadata = execution.get("metadata", {}) or {}
    status = execution.get("status", "running")

    # Progress calculation
    total_steps = metadata.get("total_steps", 0) or 0
    current_step = metadata.get("current_step", 0) or 0
    progress_percent = int((current_step / total_steps) * 100) if total_steps > 0 else 0

    return {
        # Required fields
        "id": execution.get("id", ""),
        "tenant_id": "local",
        "status": EXECUTION_TO_CASE_STATUS.get(status, "open"),

        # Workspace association
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "group_id": None,
        "group_name": None,

        # Title/summary
        "title": f"{execution.get('playbook_code', 'Unknown')} execution",
        "summary": metadata.get("summary", ""),

        # Progress
        "progress_percent": progress_percent,
        "checklist_done": current_step,
        "checklist_total": total_steps,

        # Owner/assignees
        "owner_user_id": owner_user_id,
        "owner_name": None,
        "owner_avatar": None,
        "assignees": [],

        # Priority/due date (not supported in Local-Core)
        "priority": 0,
        "due_at": None,
        "is_overdue": False,

        # Statistics
        "open_assignments_count": tasks_count,
        "artifacts_count": 0,
        "threads_count": 0,

        # Recent activity
        "last_activity_type": status,
        "last_activity_at": _parse_datetime(execution.get("updated_at")),
        "last_activity_by": None,

        # Actions/tags
        "available_actions": _get_case_actions(status),
        "tags": [execution.get("playbook_code", "")] if execution.get("playbook_code") else [],

        # Timestamps
        "created_at": _parse_datetime(execution.get("created_at")) or datetime.utcnow(),
        "updated_at": _parse_datetime(execution.get("updated_at")) or datetime.utcnow(),
    }


def map_task_to_assignment(
    task: Any,
    workspace_id: str,
    workspace_name: str,
    owner_user_id: str
) -> Dict[str, Any]:
    """
    Task -> AssignmentCardDTO complete field mapping

    Explicitly defines source for each field
    """
    exec_context = task.execution_context or {}
    status = task.status.value if hasattr(task.status, 'value') else str(task.status)

    return {
        # Required fields
        "id": task.id,
        "status": TASK_TO_ASSIGNMENT_STATUS.get(status, "pending"),

        # Case association
        "case_id": task.execution_id,
        "case_title": exec_context.get("playbook_code", ""),
        "case_group_id": None,
        "case_group_name": None,

        # Workspace association
        "source_workspace_id": workspace_id,
        "source_workspace_name": workspace_name,
        "target_workspace_id": workspace_id,
        "target_workspace_name": workspace_name,

        # Title/description
        "title": task.task_type,
        "description": task.params.get("description", "") if task.params else "",

        # Review status (not supported in Local-Core)
        "review_status": None,

        # Priority/due date (not supported in Local-Core)
        "priority": 0,
        "due_at": None,
        "is_overdue": False,

        # Assignee
        "claimed_by_user_id": owner_user_id if status == "running" else None,
        "claimed_by_name": None,
        "claimed_by_avatar": None,
        "delegated_by_user_id": None,
        "delegated_by_name": None,
        "delegated_by_avatar": None,

        # Artifacts (not supported in Local-Core)
        "required_artifacts": [],
        "submitted_artifacts": [],

        # Actions
        "available_actions": _get_assignment_actions(status),

        # Routing (not supported in Local-Core)
        "hop_count": 1,
        "max_hops": 1,
        "routing_reason": None,

        # Timestamps
        "created_at": task.created_at,
        "claimed_at": task.started_at,
        "completed_at": task.completed_at,
    }


def _get_case_actions(status: str) -> list:
    """Return available actions based on status"""
    actions_map = {
        "open": ["open", "run_playbook"],
        "blocked": ["open", "retry"],
        "completed": ["open"],
        "cancelled": ["open"],
    }
    case_status = EXECUTION_TO_CASE_STATUS.get(status, "open")
    return actions_map.get(case_status, [])


def _get_assignment_actions(status: str) -> list:
    """Return available actions based on status"""
    actions_map = {
        "pending": ["view_detail"],
        "in_progress": ["view_detail"],
        "completed": ["view_detail"],
        "failed": ["view_detail", "retry"],
        "cancelled": ["view_detail"],
    }
    assignment_status = TASK_TO_ASSIGNMENT_STATUS.get(status, "pending")
    return actions_map.get(assignment_status, [])


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except:
            return None
    return None

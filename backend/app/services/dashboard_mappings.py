"""
Dashboard data mapping constants
Defines complete field mapping from Local-Core tables to Dashboard DTOs
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


# ==================== Status Mappings ====================

# Playbook Execution Status -> Case Status
EXECUTION_TO_CASE_STATUS: Dict[str, str] = {
    "running": "open",
    "paused": "blocked",
    "done": "completed",
    "failed": "blocked",
    "cancelled": "cancelled",
}

# ==================== Field Mappings ====================


def map_execution_to_case(
    execution: Dict[str, Any],
    workspace_id: str,
    workspace_name: str,
    owner_user_id: str,
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
        "open_assignments_count": 0,
        "artifacts_count": 0,
        "threads_count": 0,
        # Recent activity
        "last_activity_type": status,
        "last_activity_at": _parse_datetime(execution.get("updated_at")),
        "last_activity_by": None,
        # Actions/tags
        "available_actions": _get_case_actions(status),
        "tags": (
            [execution.get("playbook_code", "")]
            if execution.get("playbook_code")
            else []
        ),
        # Timestamps
        "created_at": _parse_datetime(execution.get("created_at")) or _utc_now(),
        "updated_at": _parse_datetime(execution.get("updated_at")) or _utc_now(),
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

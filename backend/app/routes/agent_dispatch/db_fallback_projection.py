"""Pure projection helpers for DB fallback dispatch rows."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple


def json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def insert_failed_result(execution_id: str, exc: Exception) -> Dict[str, Any]:
    return {
        "execution_id": execution_id,
        "status": "failed",
        "error": f"Cross-worker DB fallback failed: {exc}",
    }


def timeout_result(execution_id: str, timeout: float) -> Dict[str, Any]:
    return {
        "execution_id": execution_id,
        "status": "timeout",
        "error": f"No activity for {timeout:.0f}s (cross-worker)",
    }


def consumer_dispatch_failed_result(exec_id: str, exc: Exception) -> Dict[str, Any]:
    return {
        "execution_id": exec_id,
        "status": "failed",
        "error": f"Consumer dispatch failed: {exc}",
    }


def pending_result_from_row(row: Optional[Tuple[Any, Any, Any]]) -> Tuple[Any, Any, Any]:
    if not row:
        return None, None, None
    result_data, status, progress_at = row
    if status == "done" and result_data is not None:
        return json_value(result_data), status, progress_at
    return None, status, progress_at


def pending_record_from_row(row: Optional[Tuple[Any, Any, Any, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    workspace_id, payload_data, status, result_data = row
    return {
        "workspace_id": workspace_id,
        "payload": json_value(payload_data),
        "status": status,
        "result_data": json_value(result_data),
    }


def pending_dispatch_task(exec_id: str, ws_id: str, payload_data: Any) -> Dict[str, Any]:
    return {
        "execution_id": exec_id,
        "workspace_id": ws_id,
        "payload": json_value(payload_data),
    }

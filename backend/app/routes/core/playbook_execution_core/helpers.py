import os
from typing import Any, Dict, Optional

from fastapi import HTTPException

from .state import logger

def _safe_screenshot_basename(value: str) -> str:
    """
    Accept only a plain filename (no path separators).
    """
    name = (value or "").strip()
    name = os.path.basename(name)
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid file name")
    # Only allow common screenshot types we generate.
    if not (name.endswith(".png") or name.endswith(".jpg") or name.endswith(".jpeg")):
        raise HTTPException(status_code=400, detail="Unsupported file type")
    # Basic character allowlist to avoid weird path tricks.
    for ch in name:
        if ch.isalnum() or ch in "._-":
            continue
        raise HTTPException(status_code=400, detail="Invalid file name")
    return name


def _load_landed_workflow_result(execution_id: str) -> Optional[Dict[str, Any]]:
    try:
        from backend.app.services.task_result_landing import TaskResultLandingService

        landed = TaskResultLandingService().get_landed_result(execution_id)
    except Exception:
        logger.warning(
            "get_playbook_result: failed to load landed result for %s",
            execution_id,
            exc_info=True,
        )
        return None

    if not isinstance(landed, dict):
        return None
    result_json = landed.get("result_json")
    if isinstance(result_json, dict):
        return result_json
    return None

"""Landed result readback helpers."""

import json
import pathlib
from typing import Any, Dict, Optional


def get_landed_result(
    *,
    artifacts_store: Any,
    tasks_store: Any,
    execution_id: str,
) -> Optional[Dict[str, Any]]:
    """Retrieve a previously landed result by execution_id."""
    try:
        artifact = artifacts_store.get_by_execution_id(execution_id)
    except Exception:
        artifact = None

    if not artifact:
        task = tasks_store.get_task_by_execution_id(execution_id)
        if task:
            return {
                "execution_id": execution_id,
                "status": task.status if hasattr(task, "status") else "unknown",
                "storage_ref": None,
                "summary": None,
                "result_json": getattr(task, "result", None),
                "attachments": [],
            }
        return None

    result: Dict[str, Any] = {
        "execution_id": execution_id,
        "status": "completed",
        "storage_ref": artifact.storage_ref,
        "summary": artifact.summary,
        "result_json": artifact.content,
        "attachments": [],
        "artifact_id": artifact.id,
    }

    if artifact.storage_ref:
        result_json_path = pathlib.Path(artifact.storage_ref) / "result.json"
        if result_json_path.exists():
            try:
                with result_json_path.open("r", encoding="utf-8") as file_obj:
                    result["result_json"] = json.load(file_obj)
            except Exception:
                pass

        attachment_dir = pathlib.Path(artifact.storage_ref) / "attachments"
        if attachment_dir.exists():
            for path in attachment_dir.iterdir():
                if path.is_file():
                    result["attachments"].append(
                        {
                            "filename": path.name,
                            "path": str(path),
                            "size_bytes": path.stat().st_size,
                        }
                    )

    return result

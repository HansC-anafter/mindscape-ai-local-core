"""TaskIR artifact extraction helpers for PipelineCore."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def clean_string(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def append_unique(values: List[str], value: Optional[str]) -> None:
    if value and value not in values:
        values.append(value)


def artifact_file_path(payload: Dict[str, Any]) -> Optional[str]:
    metadata = as_dict(payload.get("metadata"))
    for key in ("actual_file_path", "file_path", "storage_ref"):
        value = payload.get(key) or metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    uri = payload.get("uri")
    if isinstance(uri, str) and uri.startswith("/"):
        return uri
    return None


def task_ir_artifact_payloads(task_ir: Any) -> List[Dict[str, Any]]:
    return [
        as_dict(artifact)
        for artifact in list(getattr(task_ir, "artifacts", []) or [])
    ]

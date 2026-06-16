"""Helpers for generated artifact summary sidecars."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SUMMARY_SIDECAR_MODE_ENV = "ARTIFACT_SUMMARY_SIDECAR_MODE"


def summary_sidecar_mode() -> str:
    """Return the configured summary sidecar mode."""
    return os.getenv(SUMMARY_SIDECAR_MODE_ENV, "lazy").strip().lower() or "lazy"


def should_write_eager_summary() -> bool:
    """Return True when new landings should write physical summary.md files."""
    return summary_sidecar_mode() == "eager"


def build_summary_markdown(
    *,
    execution_id: str,
    workspace_id: str,
    task_id: Optional[str],
    thread_id: Optional[str],
    project_id: Optional[str],
    summary: Optional[str],
    landed_at: Optional[datetime] = None,
) -> str:
    """Build the derived markdown summary for a landed result."""
    effective_landed_at = landed_at or datetime.now(timezone.utc)
    md_lines = [
        f"# Execution {execution_id}",
        "",
        f"- Landed at: {effective_landed_at.isoformat()}",
        f"- workspace_id: {workspace_id}",
        f"- task_id: {task_id or '(none)'}",
        f"- thread_id: {thread_id or '(none)'}",
        f"- project_id: {project_id or '(none)'}",
        "",
        "## Summary",
        "",
        summary or "(no summary)",
        "",
    ]
    return "\n".join(md_lines)


def resolve_landing_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize nested and legacy flat landing metadata into one shape."""
    if not isinstance(metadata, dict):
        return {}
    landing = metadata.get("landing")
    nested = landing if isinstance(landing, dict) else {}

    def first_value(nested_key: str, flat_key: str) -> Any:
        value = nested.get(nested_key)
        if value is not None:
            return value
        return metadata.get(flat_key)

    return {
        "artifact_dir": first_value("artifact_dir", "landing_artifact_dir"),
        "result_json_path": first_value(
            "result_json_path",
            "landing_result_json_path",
        ),
        "summary_md_path": first_value("summary_md_path", "landing_summary_md_path"),
        "attachments_count": first_value(
            "attachments_count",
            "landing_attachments_count",
        ),
        "attachments": first_value("attachments", "landing_attachments"),
        "landed_at": first_value("landed_at", "landing_landed_at"),
    }


def summary_path_for_candidate(
    storage_ref: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Resolve a candidate summary.md path without scanning directories."""
    landing = resolve_landing_metadata(metadata or {})
    summary_path = landing.get("summary_md_path")
    if isinstance(summary_path, str) and summary_path.strip():
        return Path(summary_path.strip())
    if isinstance(storage_ref, str) and storage_ref.strip():
        return Path(storage_ref.strip()) / "summary.md"
    return None

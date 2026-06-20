"""Filesystem landing helpers for task result landing."""

import json
import os
import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.artifact_lifecycle.summary_sidecar import (
    build_summary_markdown,
    should_write_eager_summary,
)


@dataclass
class FileLandingResult:
    """Result of filesystem landing work."""

    artifact_dir: str = ""
    result_json_path: str = ""
    summary_md_path: str = ""
    attachments: List[str] = field(default_factory=list)


def land_result_files(
    *,
    storage_base_path: Optional[str],
    artifacts_dirname: str,
    execution_id: str,
    workspace_id: str,
    task_id: Optional[str],
    thread_id: Optional[str],
    project_id: Optional[str],
    summary: str,
    result_json: Dict[str, Any],
    attachments_input: List[Dict[str, Any]],
    landed_at: datetime,
) -> FileLandingResult:
    """Write result JSON, summary, and attachments to the workspace filesystem."""
    if not storage_base_path:
        return FileLandingResult()

    storage_base = pathlib.Path(storage_base_path).expanduser().resolve()
    artifact_dir = storage_base / artifacts_dirname / execution_id
    attachment_dir = artifact_dir / "attachments"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    result_json_path = artifact_dir / "result.json"
    with result_json_path.open("w", encoding="utf-8") as file_obj:
        json.dump(result_json, file_obj, ensure_ascii=False, indent=2, default=str)

    summary_md_path = artifact_dir / "summary.md"
    if should_write_eager_summary():
        summary_md_path.write_text(
            build_summary_markdown(
                execution_id=execution_id,
                workspace_id=workspace_id,
                task_id=task_id,
                thread_id=thread_id,
                project_id=project_id,
                summary=summary,
                landed_at=landed_at,
            ),
            encoding="utf-8",
        )

    written_attachments: List[str] = []
    for attachment in attachments_input:
        filename = (attachment.get("filename") or "").strip()
        if not filename:
            continue
        safe_name = os.path.basename(filename)
        content = attachment.get("content")
        if content is None:
            continue
        attachment_dir.mkdir(parents=True, exist_ok=True)
        out_path = attachment_dir / safe_name
        if isinstance(content, str):
            out_path.write_text(content, encoding="utf-8")
        else:
            out_path.write_bytes(content)
        written_attachments.append(str(out_path))

    return FileLandingResult(
        artifact_dir=str(artifact_dir),
        result_json_path=str(result_json_path),
        summary_md_path=str(summary_md_path),
        attachments=written_attachments,
    )

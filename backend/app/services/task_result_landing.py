"""
Task Result Landing Service

Persists task execution results to the workspace filesystem and creates
corresponding DB records (Artifact + Task update). This is the bridge
between the in-memory dispatch manager and durable storage.

Flow:  submit_result() -> land_result() -> files on disk + DB records
"""

import json
import logging
import os
import pathlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.workspace import (
    Artifact,
    ArtifactType,
    PrimaryActionType,
    TaskStatus,
)
from app.services.stores.tasks_store import TasksStore
from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


@dataclass
class LandingResult:
    """Result of a successful landing operation."""

    artifact_dir: str
    result_json_path: str
    summary_md_path: str
    attachments: List[str] = field(default_factory=list)
    artifact_id: Optional[str] = None


class TaskResultLandingService:
    """
    Persist task execution results as workspace artifacts.

    Writes structured files to disk and creates/updates DB records.
    Designed to be called best-effort (failures are logged, not raised).
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._tasks_store = TasksStore(db_path=db_path)
        self._artifacts_store = PostgresArtifactsStore()

    def land_result(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        result_data: Dict[str, Any],
        storage_base_path: Optional[str] = None,
        artifacts_dirname: str = "artifacts",
        thread_id: Optional[str] = None,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[LandingResult]:
        """
        Persist execution result to disk and DB.

        Args:
            workspace_id: Workspace that owns this task
            execution_id: Unique execution identifier
            result_data: Full result payload from the runner
            storage_base_path: Resolved workspace storage path (if None, skip file write)
            artifacts_dirname: Subdirectory name for artifacts (default: 'artifacts')
            thread_id: Optional thread association
            project_id: Optional project association
            task_id: Optional task ID (looked up by execution_id if not given)

        Returns:
            LandingResult on success, None on failure
        """
        try:
            return self._do_land(
                workspace_id=workspace_id,
                execution_id=execution_id,
                result_data=result_data,
                storage_base_path=storage_base_path,
                artifacts_dirname=artifacts_dirname,
                thread_id=thread_id,
                project_id=project_id,
                task_id=task_id,
            )
        except Exception:
            logger.exception(
                "land_result failed exec=%s workspace=%s",
                execution_id,
                workspace_id,
            )
            return None

    def _do_land(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        result_data: Dict[str, Any],
        storage_base_path: Optional[str],
        artifacts_dirname: str,
        thread_id: Optional[str],
        project_id: Optional[str],
        task_id: Optional[str],
    ) -> LandingResult:
        # --- Resolve task from DB if task_id not provided ---
        if not task_id:
            task = self._tasks_store.get_task_by_execution_id(execution_id)
            if task:
                task_id = task.id
                if not thread_id:
                    thread_id = getattr(task, "thread_id", None)
                if not project_id:
                    project_id = getattr(task, "project_id", None)

        # --- Normalize payload ---
        summary = (result_data.get("output") or "").strip()
        result_json = result_data.get("result_json") or result_data
        attachments_input = result_data.get("attachments") or []

        # --- File landing (skip if no storage_base_path) ---
        artifact_dir_str = ""
        result_json_path_str = ""
        summary_md_path_str = ""
        written_attachments: List[str] = []

        if storage_base_path:
            storage_base = pathlib.Path(storage_base_path).expanduser().resolve()
            artifact_dir = storage_base / artifacts_dirname / execution_id
            attachment_dir = artifact_dir / "attachments"
            artifact_dir.mkdir(parents=True, exist_ok=True)

            # Write result.json
            result_json_path = artifact_dir / "result.json"
            with result_json_path.open("w", encoding="utf-8") as f:
                json.dump(result_json, f, ensure_ascii=False, indent=2, default=str)

            # Write summary.md
            summary_md_path = artifact_dir / "summary.md"
            md_lines = [
                f"# Execution {execution_id}",
                "",
                f"- Landed at: {_utc_now().isoformat()}",
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
            summary_md_path.write_text("\n".join(md_lines), encoding="utf-8")

            # Write attachments
            for att in attachments_input:
                filename = (att.get("filename") or "").strip()
                if not filename:
                    continue
                safe_name = os.path.basename(filename)
                content = att.get("content")
                if content is None:
                    continue
                attachment_dir.mkdir(parents=True, exist_ok=True)
                out_path = attachment_dir / safe_name
                if isinstance(content, str):
                    out_path.write_text(content, encoding="utf-8")
                else:
                    out_path.write_bytes(content)
                written_attachments.append(str(out_path))

            artifact_dir_str = str(artifact_dir)
            result_json_path_str = str(result_json_path)
            summary_md_path_str = str(summary_md_path)

            logger.info(
                "Files landed: dir=%s attachments=%d",
                artifact_dir_str,
                len(written_attachments),
            )

        # --- DB: Create Artifact record (idempotent by execution_id) ---
        artifact_id = None
        try:
            existing = self._artifacts_store.get_by_execution_id(execution_id)
            if existing:
                # Update storage_ref if we now have it
                if artifact_dir_str:
                    self._artifacts_store.update_artifact(
                        existing.id,
                        storage_ref=artifact_dir_str,
                        summary=summary[:2000] if summary else existing.summary,
                    )
                artifact_id = existing.id
                logger.info("Artifact already exists id=%s, updated", artifact_id)
            else:
                artifact_id = str(uuid.uuid4())
                artifact = Artifact(
                    id=artifact_id,
                    workspace_id=workspace_id,
                    task_id=task_id,
                    execution_id=execution_id,
                    thread_id=thread_id,
                    playbook_code="external_agent",
                    artifact_type=ArtifactType.DATA,
                    title=f"Task Result: {execution_id[:8]}",
                    summary=summary[:2000] if summary else "(no summary)",
                    content={"output": summary[:500]} if summary else {},
                    storage_ref=artifact_dir_str or None,
                    primary_action_type=PrimaryActionType.DOWNLOAD,
                    metadata={
                        "project_id": project_id,
                        "source": "task_runner",
                        "has_attachments": len(written_attachments) > 0,
                    },
                )
                self._artifacts_store.create_artifact(artifact)
                logger.info("Artifact created id=%s exec=%s", artifact_id, execution_id)
        except Exception:
            logger.exception("Artifact DB write failed exec=%s", execution_id)

        # --- DB: Update Task status ---
        if task_id:
            try:
                self._tasks_store.update_task_status(
                    task_id=task_id,
                    status=TaskStatus.SUCCEEDED,
                    result={
                        "summary": summary[:500],
                        "storage_ref": artifact_dir_str or None,
                        "execution_id": execution_id,
                        "artifact_id": artifact_id,
                    },
                    completed_at=_utc_now(),
                )
                logger.info("Task updated id=%s status=succeeded", task_id)
            except Exception:
                logger.exception("Task DB update failed task_id=%s", task_id)

        return LandingResult(
            artifact_dir=artifact_dir_str,
            result_json_path=result_json_path_str,
            summary_md_path=summary_md_path_str,
            attachments=written_attachments,
            artifact_id=artifact_id,
        )

    def get_landed_result(
        self,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a previously landed result by execution_id.

        Returns a dict with status, storage_ref, summary, result_json, attachments.
        """
        # Try DB first
        try:
            artifact = self._artifacts_store.get_by_execution_id(execution_id)
        except Exception:
            artifact = None

        if not artifact:
            # Check if task exists but no artifact yet
            task = self._tasks_store.get_task_by_execution_id(execution_id)
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

        # Read full result.json from disk if available
        if artifact.storage_ref:
            result_json_path = pathlib.Path(artifact.storage_ref) / "result.json"
            if result_json_path.exists():
                try:
                    with result_json_path.open("r", encoding="utf-8") as f:
                        result["result_json"] = json.load(f)
                except Exception:
                    pass

            # Index attachments
            att_dir = pathlib.Path(artifact.storage_ref) / "attachments"
            if att_dir.exists():
                for p in att_dir.iterdir():
                    if p.is_file():
                        result["attachments"].append(
                            {
                                "filename": p.name,
                                "path": str(p),
                                "size_bytes": p.stat().st_size,
                            }
                        )

        return result

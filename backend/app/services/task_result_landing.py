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
from datetime import datetime, timedelta, timezone
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


def _clean_string(value: Any) -> Optional[str]:
    """Return a trimmed string or None when the value is empty/non-string."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


@dataclass
class LandingResult:
    """Result of a successful landing operation."""

    artifact_dir: str
    result_json_path: str
    summary_md_path: str
    attachments: List[str] = field(default_factory=list)
    artifact_id: Optional[str] = None
    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    failure: Dict[str, Any] = field(default_factory=dict)


class TaskResultLandingService:
    """
    Persist task execution results as workspace artifacts.

    Writes structured files to disk and creates/updates DB records.
    Designed to be called best-effort (failures are logged, not raised).
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._tasks_store = TasksStore()
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
        # --- Recover lineage from result payload / task record ---
        result_context = (result_data.get("context") or {}) if result_data else {}
        result_metadata = (result_data.get("metadata") or {}) if result_data else {}

        if not thread_id:
            thread_id = result_context.get("thread_id") or result_metadata.get(
                "thread_id"
            )
        if not project_id:
            project_id = result_context.get("project_id") or result_metadata.get(
                "project_id"
            )

        task = None
        if task_id:
            task = self._tasks_store.get_task(task_id)
        if not task:
            task = self._tasks_store.get_task_by_execution_id(execution_id)

        if task:
            task_id = task.id
            execution_context = getattr(task, "execution_context", None) or {}
            task_params = getattr(task, "params", None) or {}
            task_context = (task_params.get("context") or {}) if task_params else {}

            if not thread_id:
                thread_id = (
                    execution_context.get("thread_id")
                    or task_params.get("thread_id")
                    or task_context.get("thread_id")
                )
            if not project_id:
                project_id = (
                    getattr(task, "project_id", None)
                    or execution_context.get("project_id")
                    or task_params.get("project_id")
                    or task_context.get("project_id")
                )

        # --- Normalize payload ---
        summary = (result_data.get("output") or "").strip()
        result_json = result_data.get("result_json") or result_data
        attachments_input = result_data.get("attachments") or []
        initial_attachment_filenames = self._extract_attachment_filenames(attachments_input)
        deliverable_identity = self._resolve_deliverable_identity(
            result_data=result_data,
            result_json=result_json if isinstance(result_json, dict) else {},
            result_context=result_context,
            result_metadata=result_metadata,
            task=task,
            attachment_filenames=initial_attachment_filenames,
        )
        derived_attachments = self._derive_execution_trace_attachments(
            result_data=result_data,
            deliverable_identity=deliverable_identity,
            task=task,
        )
        if derived_attachments:
            attachments_input = list(attachments_input) + derived_attachments
            deliverable_identity = self._resolve_deliverable_identity(
                result_data=result_data,
                result_json=result_json if isinstance(result_json, dict) else {},
                result_context=result_context,
                result_metadata=result_metadata,
                task=task,
                attachment_filenames=self._extract_attachment_filenames(attachments_input),
            )
        attachment_filenames = self._extract_attachment_filenames(attachments_input)
        preferred_artifact_title = (
            deliverable_identity.get("artifact_title")
            or f"Task Result: {execution_id[:8]}"
        )

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

        markdown_failure = self._build_markdown_deliverable_failure(
            deliverable_identity=deliverable_identity,
            attachment_filenames=attachment_filenames,
            result_data=result_data,
        )
        if markdown_failure:
            logger.warning(
                "Markdown deliverable landing failed exec=%s missing=%s",
                execution_id,
                markdown_failure.get("missing_deliverables") or [],
            )
            return LandingResult(
                artifact_dir=artifact_dir_str,
                result_json_path=result_json_path_str,
                summary_md_path=summary_md_path_str,
                attachments=written_attachments,
                success=False,
                error_code=str(markdown_failure.get("error_code") or ""),
                error_message=str(markdown_failure.get("message") or ""),
                failure=markdown_failure,
            )

        # --- DB: Create Artifact record (idempotent by execution_id) ---
        artifact_id = None
        landed_at = _utc_now()
        landing_metadata = self._build_landing_metadata(
            artifact_dir=artifact_dir_str,
            result_json_path=result_json_path_str,
            summary_md_path=summary_md_path_str,
            attachments=written_attachments,
            attachment_filenames=attachment_filenames,
            landed_at=landed_at,
        )
        try:
            existing = self._artifacts_store.get_by_execution_id(execution_id)
            if existing:
                updated_metadata = self._merge_artifact_metadata(
                    existing_metadata=getattr(existing, "metadata", None),
                    project_id=project_id,
                    has_attachments=len(written_attachments) > 0,
                    landing_metadata=landing_metadata,
                    deliverable_identity=deliverable_identity,
                )
                update_kwargs = {
                    "summary": summary[:2000] if summary else existing.summary,
                    "metadata": updated_metadata,
                }
                if self._should_override_artifact_title(existing.title):
                    update_kwargs["title"] = preferred_artifact_title
                if artifact_dir_str:
                    update_kwargs["storage_ref"] = artifact_dir_str
                self._artifacts_store.update_artifact(existing.id, **update_kwargs)
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
                    title=preferred_artifact_title,
                    summary=summary[:2000] if summary else "(no summary)",
                    content={"output": summary[:500]} if summary else {},
                    storage_ref=artifact_dir_str or None,
                    primary_action_type=PrimaryActionType.DOWNLOAD,
                    metadata=self._merge_artifact_metadata(
                        existing_metadata=None,
                        project_id=project_id,
                        has_attachments=len(written_attachments) > 0,
                        landing_metadata=landing_metadata,
                        deliverable_identity=deliverable_identity,
                    ),
                )
                self._artifacts_store.create_artifact(artifact)
                logger.info("Artifact created id=%s exec=%s", artifact_id, execution_id)
        except Exception:
            logger.exception("Artifact DB write failed exec=%s", execution_id)

        # --- DB: Update Task status ---
        if task_id:
            try:
                existing_task_result = (
                    dict(getattr(task, "result", {}) or {})
                    if isinstance(getattr(task, "result", None), dict)
                    else {}
                )
                self._tasks_store.update_task_status(
                    task_id=task_id,
                    status=TaskStatus.SUCCEEDED,
                    result=self._build_task_result_payload(
                        existing_result=existing_task_result,
                        incoming_result=result_data,
                        summary=summary[:500],
                        storage_ref=artifact_dir_str or None,
                        execution_id=execution_id,
                        artifact_id=artifact_id,
                        landing_metadata=landing_metadata,
                        deliverable_identity=deliverable_identity,
                    ),
                    completed_at=landed_at,
                )
                logger.info("Task updated id=%s status=succeeded", task_id)
            except Exception:
                logger.exception("Task DB update failed task_id=%s", task_id)

        # --- Workspace data_sources: write-time aggregation ---
        pack_id = getattr(task, "pack_id", None) if task else None
        if pack_id and workspace_id:
            try:
                from app.services.stores.postgres.workspaces_store import (
                    PostgresWorkspacesStore,
                )
                from app.services.manifest_utils import resolve_playbook_produces

                result_summary = self._extract_result_summary(result_data)
                produces = resolve_playbook_produces(pack_id)
                entry = {
                    "last_run": _utc_now().isoformat(),
                    "last_result_summary": result_summary,
                }
                if produces:
                    entry["produces"] = [
                        {"type": p.get("type"), "label": p.get("label", "")}
                        for p in produces
                        if isinstance(p, dict) and p.get("type")
                    ]
                PostgresWorkspacesStore().merge_data_sources(
                    workspace_id=workspace_id,
                    pack_id=pack_id,
                    entry=entry,
                )
            except Exception:
                logger.debug(
                    "data_sources merge skipped exec=%s: %s",
                    execution_id,
                    "error",
                    exc_info=True,
                )

        return LandingResult(
            artifact_dir=artifact_dir_str,
            result_json_path=result_json_path_str,
            summary_md_path=summary_md_path_str,
            attachments=written_attachments,
            artifact_id=artifact_id,
        )

    @staticmethod
    def _extract_result_summary(result_data: Dict[str, Any]) -> str:
        """Extract a compact metrics summary from task result payload.

        Looks for common output keys (processed, created, tagged, etc.)
        and formats them as a short string for workspace data_sources.
        """
        if not result_data:
            return ""
        # Try steps -> first step -> outputs
        steps = result_data.get("steps") or {}
        for step_data in steps.values():
            outputs = step_data.get("outputs") or step_data.get("step_outputs", {})
            if isinstance(outputs, dict):
                # Flatten nested step_outputs
                flat = {}
                for v in outputs.values():
                    if isinstance(v, dict):
                        flat.update(v)
                    else:
                        flat = outputs
                        break
                if flat:
                    parts = [f"{k}={v}" for k, v in flat.items() if v is not None]
                    if parts:
                        return ", ".join(parts[:5])
        # Fallback: status
        status = result_data.get("status")
        return str(status) if status else ""

    @staticmethod
    def _extract_attachment_filenames(attachments_input: List[Dict[str, Any]]) -> List[str]:
        filenames: List[str] = []
        seen: set[str] = set()
        for att in attachments_input or []:
            if not isinstance(att, dict):
                continue
            safe_name = _clean_string(os.path.basename(att.get("filename") or ""))
            if safe_name and safe_name not in seen:
                filenames.append(safe_name)
                seen.add(safe_name)
        return filenames

    @staticmethod
    def _derive_execution_trace_attachments(
        *,
        result_data: Dict[str, Any],
        deliverable_identity: Dict[str, Any],
        task: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(result_data, dict):
            return []
        if result_data.get("attachments"):
            return []

        execution_trace = result_data.get("execution_trace")
        if not isinstance(execution_trace, dict):
            execution_trace = {}

        sandbox_roots = TaskResultLandingService._resolve_attachment_snapshot_roots(
            result_data=result_data,
            execution_trace=execution_trace,
        )
        if not sandbox_roots:
            return []

        desired_filenames = TaskResultLandingService._deliverable_filenames_from_identity(
            deliverable_identity
        )
        candidate_paths: List[str] = []
        identity_probe_paths = TaskResultLandingService._deliverable_probe_paths_from_identity(
            deliverable_identity
        )
        identity_only_paths: set[str] = set()
        for key in ("files_created", "files_modified"):
            values = execution_trace.get(key) or result_data.get(key) or []
            if isinstance(values, list):
                candidate_paths.extend(values)
        seen_candidate_paths = {
            path.strip().replace("\\", "/").lstrip("./")
            for path in candidate_paths
            if isinstance(path, str) and path.strip()
        }
        for rel_path in identity_probe_paths:
            if rel_path in seen_candidate_paths:
                continue
            candidate_paths.append(rel_path)
            identity_only_paths.add(rel_path)

        attachments: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw_path in candidate_paths:
            if not isinstance(raw_path, str):
                continue
            candidate_rel = raw_path.strip()
            if not candidate_rel:
                continue
            candidate_rel = candidate_rel.replace("\\", "/").lstrip("./")
            filename = os.path.basename(candidate_rel)
            if desired_filenames and filename not in desired_filenames:
                continue
            if filename in seen:
                continue
            resolved_file_path: Optional[pathlib.Path] = None
            for sandbox_root in sandbox_roots:
                file_path = (sandbox_root / candidate_rel).resolve()
                try:
                    file_path.relative_to(sandbox_root)
                except ValueError:
                    continue
                if not file_path.is_file():
                    continue
                if (
                    candidate_rel in identity_only_paths
                    and not TaskResultLandingService._file_matches_task_window(
                        file_path=file_path,
                        task=task,
                    )
                ):
                    continue
                resolved_file_path = file_path
                break
            if resolved_file_path is None:
                continue
            try:
                content = resolved_file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = resolved_file_path.read_bytes()
                except OSError:
                    continue
            except OSError:
                continue
            attachments.append(
                {
                    "filename": filename,
                    "content": content,
                }
            )
            seen.add(filename)

        return attachments

    @staticmethod
    def _resolve_attachment_snapshot_roots(
        *,
        result_data: Dict[str, Any],
        execution_trace: Dict[str, Any],
    ) -> List[pathlib.Path]:
        candidates: List[Any] = [
            execution_trace.get("sandbox_path"),
            execution_trace.get("effective_sandbox_path"),
        ]
        result_metadata = result_data.get("metadata") or {}
        if isinstance(result_metadata, dict):
            candidates.extend(
                [
                    result_metadata.get("effective_sandbox_path"),
                    result_metadata.get("workspace_root"),
                ]
            )

        roots: List[pathlib.Path] = []
        seen: set[pathlib.Path] = set()
        for raw_path in candidates:
            candidate = _clean_string(raw_path)
            if not candidate:
                continue
            candidate_path = pathlib.Path(candidate).expanduser().resolve()
            if not candidate_path.exists() or candidate_path in seen:
                continue
            seen.add(candidate_path)
            roots.append(candidate_path)
        return roots

    @staticmethod
    def _deliverable_probe_paths_from_identity(
        deliverable_identity: Dict[str, Any],
    ) -> List[str]:
        paths: List[str] = []
        seen: set[str] = set()

        def _add(raw_value: Any) -> None:
            if not isinstance(raw_value, str):
                return
            normalized = raw_value.strip().replace("\\", "/").lstrip("./")
            if not normalized:
                return
            for candidate in (normalized, os.path.basename(normalized)):
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                paths.append(candidate)

        _add(deliverable_identity.get("deliverable_path"))
        deliverable_targets = deliverable_identity.get("deliverable_targets")
        if isinstance(deliverable_targets, list):
            for target in deliverable_targets:
                if isinstance(target, dict):
                    _add(target.get("deliverable_path"))
        return paths

    @staticmethod
    def _coerce_utc_datetime(value: Any) -> Optional[datetime]:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _file_matches_task_window(
        *,
        file_path: pathlib.Path,
        task: Optional[Any],
    ) -> bool:
        if task is None:
            return True
        try:
            stat = file_path.stat()
        except OSError:
            return False

        file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        started_at = TaskResultLandingService._coerce_utc_datetime(
            getattr(task, "started_at", None)
        ) or TaskResultLandingService._coerce_utc_datetime(
            getattr(task, "created_at", None)
        )

        if started_at and file_mtime < (started_at - timedelta(seconds=2)):
            return False
        return True

    @staticmethod
    def _deliverable_filenames_from_identity(
        deliverable_identity: Dict[str, Any],
    ) -> set[str]:
        filenames: set[str] = set()
        deliverable_path = _clean_string(deliverable_identity.get("deliverable_path"))
        if deliverable_path:
            filenames.add(os.path.basename(deliverable_path))
        deliverable_targets = deliverable_identity.get("deliverable_targets")
        if isinstance(deliverable_targets, list):
            for target in deliverable_targets:
                if not isinstance(target, dict):
                    continue
                target_path = _clean_string(target.get("deliverable_path"))
                if target_path:
                    filenames.add(os.path.basename(target_path))
        return filenames

    @staticmethod
    def _expected_markdown_deliverables(
        deliverable_identity: Dict[str, Any],
    ) -> List[str]:
        return sorted(
            filename
            for filename in TaskResultLandingService._deliverable_filenames_from_identity(
                deliverable_identity
            )
            if filename.lower().endswith(".md")
        )

    @staticmethod
    def _build_markdown_deliverable_failure(
        *,
        deliverable_identity: Dict[str, Any],
        attachment_filenames: List[str],
        result_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        expected_deliverables = TaskResultLandingService._expected_markdown_deliverables(
            deliverable_identity
        )
        if not expected_deliverables:
            return None

        landed_filenames = {
            _clean_string(os.path.basename(filename))
            for filename in attachment_filenames or []
            if _clean_string(os.path.basename(filename))
        }
        missing_deliverables = [
            filename
            for filename in expected_deliverables
            if filename not in landed_filenames
        ]
        if not missing_deliverables:
            return None

        execution_trace = (
            result_data.get("execution_trace")
            if isinstance(result_data, dict)
            else {}
        ) or {}
        files_created = execution_trace.get("files_created") or result_data.get(
            "files_created"
        ) or []
        files_modified = execution_trace.get("files_modified") or result_data.get(
            "files_modified"
        ) or []
        return {
            "error_code": "deliverable_file_missing",
            "message": (
                "Required markdown deliverables did not land as file-backed attachments"
            ),
            "expected_deliverables": expected_deliverables,
            "missing_deliverables": missing_deliverables,
            "attachment_filenames": list(attachment_filenames or []),
            "files_created": list(files_created) if isinstance(files_created, list) else [],
            "files_modified": list(files_modified)
            if isinstance(files_modified, list)
            else [],
        }

    @staticmethod
    def _resolve_deliverable_identity(
        *,
        result_data: Dict[str, Any],
        result_json: Dict[str, Any],
        result_context: Dict[str, Any],
        result_metadata: Dict[str, Any],
        task: Optional[Any],
        attachment_filenames: List[str],
    ) -> Dict[str, Any]:
        task_execution_context = getattr(task, "execution_context", None) or {}
        task_params = getattr(task, "params", None) or {}
        task_result = getattr(task, "result", None) or {}
        task_param_context = (
            task_params.get("context")
            if isinstance(task_params, dict)
            else {}
        ) or {}
        result_json_context = (
            result_json.get("context")
            if isinstance(result_json, dict)
            else {}
        ) or {}
        result_json_metadata = (
            result_json.get("metadata")
            if isinstance(result_json, dict)
            else {}
        ) or {}
        task_execution_inputs = (
            task_execution_context.get("inputs")
            if isinstance(task_execution_context, dict)
            else {}
        ) or {}
        task_input_params = (
            task_params.get("input_params")
            if isinstance(task_params, dict)
            else {}
        ) or {}
        result_context_inputs = (
            result_context.get("inputs")
            if isinstance(result_context, dict)
            else {}
        ) or {}
        result_metadata_inputs = (
            result_metadata.get("inputs")
            if isinstance(result_metadata, dict)
            else {}
        ) or {}
        result_json_context_inputs = (
            result_json_context.get("inputs")
            if isinstance(result_json_context, dict)
            else {}
        ) or {}
        result_json_metadata_inputs = (
            result_json_metadata.get("inputs")
            if isinstance(result_json_metadata, dict)
            else {}
        ) or {}

        candidate_mappings = [
            result_data,
            result_context,
            result_metadata,
            result_json,
            result_json_context,
            result_json_metadata,
            task_execution_context,
            task_execution_inputs,
            task_params,
            task_input_params,
            task_param_context,
            task_result,
            result_context_inputs,
            result_metadata_inputs,
            result_json_context_inputs,
            result_json_metadata_inputs,
        ]

        deliverable_path = None
        deliverable_name = None
        deliverable_targets = []
        for candidate in candidate_mappings:
            if not isinstance(candidate, dict):
                continue
            if deliverable_path is None:
                deliverable_path = _clean_string(candidate.get("deliverable_path"))
            if deliverable_name is None:
                deliverable_name = _clean_string(candidate.get("deliverable_name"))
            if not deliverable_targets:
                deliverable_targets = TaskResultLandingService._extract_deliverable_targets(
                    candidate
                )
            if deliverable_path and deliverable_name:
                break

        if (deliverable_path is None or deliverable_name is None) and deliverable_targets:
            primary_target = deliverable_targets[0]
            if deliverable_path is None:
                deliverable_path = _clean_string(primary_target.get("deliverable_path"))
            if deliverable_name is None:
                deliverable_name = _clean_string(primary_target.get("deliverable_name"))

        artifact_title = None
        title_source = None
        if attachment_filenames:
            artifact_title = attachment_filenames[0]
            title_source = "attachment_filename"
        elif deliverable_path:
            artifact_title = os.path.basename(deliverable_path)
            title_source = "deliverable_path"
        elif deliverable_name:
            artifact_title = deliverable_name
            title_source = "deliverable_name"

        identity: Dict[str, Any] = {
            "artifact_title": artifact_title,
            "attachment_filenames": list(attachment_filenames or []),
        }
        if deliverable_name:
            identity["deliverable_name"] = deliverable_name
        if deliverable_path:
            identity["deliverable_path"] = deliverable_path
        if title_source:
            identity["title_source"] = title_source
        if deliverable_targets:
            identity["deliverable_targets"] = deliverable_targets
        return identity

    @staticmethod
    def _extract_deliverable_targets(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_targets = candidate.get("deliverable_targets")
        if not isinstance(raw_targets, list):
            return []
        targets: List[Dict[str, Any]] = []
        for raw_target in raw_targets:
            if not isinstance(raw_target, dict):
                continue
            deliverable_id = _clean_string(raw_target.get("deliverable_id"))
            deliverable_name = _clean_string(raw_target.get("deliverable_name"))
            deliverable_path = _clean_string(raw_target.get("deliverable_path"))
            normalized: Dict[str, Any] = {}
            if deliverable_id is not None:
                normalized["deliverable_id"] = deliverable_id
            if deliverable_name is not None:
                normalized["deliverable_name"] = deliverable_name
            if deliverable_path is not None:
                normalized["deliverable_path"] = deliverable_path
            if normalized:
                targets.append(normalized)
        return targets

    @staticmethod
    def _build_landing_metadata(
        *,
        artifact_dir: str,
        result_json_path: str,
        summary_md_path: str,
        attachments: List[str],
        attachment_filenames: List[str],
        landed_at: datetime,
    ) -> Dict[str, Any]:
        if (
            not artifact_dir
            and not result_json_path
            and not summary_md_path
            and not attachments
            and not attachment_filenames
        ):
            return {}
        metadata = {
            "artifact_dir": artifact_dir or None,
            "result_json_path": result_json_path or None,
            "summary_md_path": summary_md_path or None,
            "attachments": list(attachments or []),
            "attachments_count": len(attachments or []),
            "landed_at": landed_at.isoformat(),
        }
        if attachment_filenames:
            metadata["attachment_filenames"] = list(attachment_filenames)
        return metadata

    @staticmethod
    def _merge_artifact_metadata(
        *,
        existing_metadata: Optional[Dict[str, Any]],
        project_id: Optional[str],
        has_attachments: bool,
        landing_metadata: Dict[str, Any],
        deliverable_identity: Dict[str, Any],
    ) -> Dict[str, Any]:
        metadata = dict(existing_metadata or {})
        metadata["source"] = metadata.get("source") or "task_runner"
        if project_id is not None:
            metadata["project_id"] = project_id
        metadata["has_attachments"] = has_attachments or bool(
            metadata.get("has_attachments")
        )
        if landing_metadata:
            metadata["landing"] = landing_metadata
        deliverable_name = _clean_string(deliverable_identity.get("deliverable_name"))
        deliverable_path = _clean_string(deliverable_identity.get("deliverable_path"))
        title_source = _clean_string(deliverable_identity.get("title_source"))
        attachment_filenames = deliverable_identity.get("attachment_filenames")
        deliverable_targets = deliverable_identity.get("deliverable_targets")
        if deliverable_name is not None:
            metadata["deliverable_name"] = deliverable_name
        if deliverable_path is not None:
            metadata["deliverable_path"] = deliverable_path
        if title_source is not None:
            metadata["deliverable_title_source"] = title_source
        if isinstance(deliverable_targets, list) and deliverable_targets:
            metadata["deliverable_targets"] = list(deliverable_targets)
        if isinstance(attachment_filenames, list) and attachment_filenames:
            metadata["attachment_filenames"] = list(attachment_filenames)
        return metadata

    @staticmethod
    def _build_task_result_payload(
        *,
        existing_result: Dict[str, Any],
        incoming_result: Dict[str, Any],
        summary: str,
        storage_ref: Optional[str],
        execution_id: str,
        artifact_id: Optional[str],
        landing_metadata: Dict[str, Any],
        deliverable_identity: Dict[str, Any],
    ) -> Dict[str, Any]:
        result_payload = dict(existing_result or {})
        result_payload.update(
            {
                "summary": summary,
                "storage_ref": storage_ref,
                "execution_id": execution_id,
                "artifact_id": artifact_id,
            }
        )
        execution_trace = incoming_result.get("execution_trace")
        if isinstance(execution_trace, dict) and execution_trace:
            result_payload["execution_trace"] = execution_trace
        if landing_metadata:
            result_payload["landing"] = landing_metadata
        deliverable_name = _clean_string(deliverable_identity.get("deliverable_name"))
        deliverable_path = _clean_string(deliverable_identity.get("deliverable_path"))
        attachment_filenames = deliverable_identity.get("attachment_filenames")
        deliverable_targets = deliverable_identity.get("deliverable_targets")
        if deliverable_name is not None:
            result_payload["deliverable_name"] = deliverable_name
        if deliverable_path is not None:
            result_payload["deliverable_path"] = deliverable_path
        if isinstance(deliverable_targets, list) and deliverable_targets:
            result_payload["deliverable_targets"] = list(deliverable_targets)
        if isinstance(attachment_filenames, list) and attachment_filenames:
            result_payload["attachment_filenames"] = list(attachment_filenames)
        return result_payload

    @staticmethod
    def _should_override_artifact_title(title: Optional[str]) -> bool:
        normalized = _clean_string(title)
        return normalized is None or normalized.startswith("Task Result:")

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

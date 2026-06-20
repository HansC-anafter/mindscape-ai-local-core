"""
Task Result Landing Service

Persists task execution results to the workspace filesystem and creates
corresponding DB records (Artifact + Task update). This is the bridge
between the in-memory dispatch manager and durable storage.

Flow:  submit_result() -> land_result() -> files on disk + DB records
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.workspace import (
    Artifact,
    ArtifactType,
    PrimaryActionType,
    TaskStatus,
)
from app.services.task_result_landing_core import (
    attachments as landing_attachments,
    common as landing_common,
    files as landing_files,
    identity as landing_identity,
    metadata as landing_metadata,
    readback as landing_readback,
    summary as landing_summary,
)
from app.services.stores.tasks_store import TasksStore
from app.services.stores.postgres.artifact_manifest_store import ArtifactManifestStore
from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from backend.app.services.result_object_contract import (
    analysis_result_object_key,
    build_result_object_descriptor,
    json_payload_size,
)

logger = logging.getLogger(__name__)
_DATA_SOURCE_SUMMARY_LIMIT = landing_common.DATA_SOURCE_SUMMARY_LIMIT
_utc_now = landing_common.utc_now
_clean_string = landing_common.clean_string


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

    _extract_result_summary = staticmethod(landing_summary.extract_result_summary)
    _compact_summary_value = staticmethod(landing_summary.compact_summary_value)
    _limit_summary_text = staticmethod(landing_summary.limit_summary_text)
    _extract_attachment_filenames = staticmethod(
        landing_attachments.extract_attachment_filenames
    )
    _derive_execution_trace_attachments = staticmethod(
        landing_attachments.derive_execution_trace_attachments
    )
    _resolve_attachment_snapshot_roots = staticmethod(
        landing_attachments.resolve_attachment_snapshot_roots
    )
    _deliverable_probe_paths_from_identity = staticmethod(
        landing_attachments.deliverable_probe_paths_from_identity
    )
    _coerce_utc_datetime = staticmethod(landing_attachments.coerce_utc_datetime)
    _file_matches_task_window = staticmethod(
        landing_attachments.file_matches_task_window
    )
    _deliverable_filenames_from_identity = staticmethod(
        landing_attachments.deliverable_filenames_from_identity
    )
    _expected_markdown_deliverables = staticmethod(
        landing_attachments.expected_markdown_deliverables
    )
    _build_markdown_deliverable_failure = staticmethod(
        landing_attachments.build_markdown_deliverable_failure
    )
    _resolve_deliverable_identity = staticmethod(
        landing_identity.resolve_deliverable_identity
    )
    _extract_deliverable_targets = staticmethod(
        landing_identity.extract_deliverable_targets
    )
    _build_landing_metadata = staticmethod(landing_metadata.build_landing_metadata)
    _merge_artifact_metadata = staticmethod(landing_metadata.merge_artifact_metadata)
    _build_artifact_content_descriptor = staticmethod(
        landing_metadata.build_artifact_content_descriptor
    )
    _build_task_result_payload = staticmethod(landing_metadata.build_task_result_payload)
    _resolve_nested_value = staticmethod(landing_metadata.resolve_nested_value)
    _has_material_value = staticmethod(landing_metadata.has_material_value)
    _first_nested_value = staticmethod(landing_metadata.first_nested_value)
    _extract_storyboard_preview_evidence = staticmethod(
        landing_metadata.extract_storyboard_preview_evidence
    )
    _extract_acceptance_evidence = staticmethod(
        landing_metadata.extract_acceptance_evidence
    )
    _extract_workflow_failure = staticmethod(landing_metadata.extract_workflow_failure)
    _should_override_artifact_title = staticmethod(
        landing_metadata.should_override_artifact_title
    )

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._tasks_store = TasksStore()
        self._artifacts_store = PostgresArtifactsStore()
        self._artifact_manifest_store = ArtifactManifestStore()

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
        execution_context: Dict[str, Any] = {}
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
        landed_at = _utc_now()
        file_landing = landing_files.land_result_files(
            storage_base_path=storage_base_path,
            artifacts_dirname=artifacts_dirname,
            execution_id=execution_id,
            workspace_id=workspace_id,
            task_id=task_id,
            thread_id=thread_id,
            project_id=project_id,
            summary=summary,
            result_json=result_json,
            attachments_input=attachments_input,
            landed_at=landed_at,
        )
        artifact_dir_str = file_landing.artifact_dir
        result_json_path_str = file_landing.result_json_path
        summary_md_path_str = file_landing.summary_md_path
        written_attachments = file_landing.attachments
        if artifact_dir_str:
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
        acceptance_evidence = self._extract_acceptance_evidence(
            result_data=result_data,
            result_json=result_json if isinstance(result_json, dict) else {},
            task=task,
        )
        workflow_failure = self._extract_workflow_failure(
            result_data=result_data,
            execution_context=execution_context,
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
        landing_metadata = self._build_landing_metadata(
            artifact_dir=artifact_dir_str,
            result_json_path=result_json_path_str,
            summary_md_path=summary_md_path_str,
            attachments=written_attachments,
            attachment_filenames=attachment_filenames,
            landed_at=landed_at,
        )
        result_object_key = analysis_result_object_key(execution_id)
        try:
            existing = self._artifacts_store.get_by_execution_id(execution_id)
            artifact_id = existing.id if existing else str(uuid.uuid4())
            artifact_descriptor = build_result_object_descriptor(
                payload=result_data,
                summary=summary[:500],
                storage_ref=artifact_dir_str or None,
                object_key=result_object_key,
                execution_id=execution_id,
                artifact_id=artifact_id,
                landing_metadata=landing_metadata,
                deliverable_identity=deliverable_identity,
                acceptance_evidence=acceptance_evidence,
            )
            artifact_content = self._build_artifact_content_descriptor(
                artifact_descriptor
            )
            if existing:
                updated_metadata = self._merge_artifact_metadata(
                    existing_metadata=getattr(existing, "metadata", None),
                    project_id=project_id,
                    has_attachments=len(written_attachments) > 0,
                    landing_metadata=landing_metadata,
                    deliverable_identity=deliverable_identity,
                    acceptance_evidence=acceptance_evidence,
                )
                update_kwargs = {
                    "summary": summary[:2000] if summary else existing.summary,
                    "content": artifact_content,
                    "metadata": updated_metadata,
                }
                if self._should_override_artifact_title(existing.title):
                    update_kwargs["title"] = preferred_artifact_title
                if artifact_dir_str:
                    update_kwargs["storage_ref"] = artifact_dir_str
                self._artifacts_store.update_artifact(existing.id, **update_kwargs)
                logger.info("Artifact already exists id=%s, updated", artifact_id)
            else:
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
                    content=artifact_content,
                    storage_ref=artifact_dir_str or None,
                    primary_action_type=PrimaryActionType.DOWNLOAD,
                    metadata=self._merge_artifact_metadata(
                        existing_metadata=None,
                        project_id=project_id,
                        has_attachments=len(written_attachments) > 0,
                        landing_metadata=landing_metadata,
                        deliverable_identity=deliverable_identity,
                        acceptance_evidence=acceptance_evidence,
                    ),
                )
                self._artifacts_store.create_artifact(artifact)
                logger.info("Artifact created id=%s exec=%s", artifact_id, execution_id)
            if result_json_path_str:
                self._artifact_manifest_store.upsert_result_manifest(
                    artifact_id=artifact_id,
                    workspace_id=workspace_id,
                    task_id=task_id,
                    execution_id=execution_id,
                    result_descriptor=artifact_descriptor,
                    storage_ref=artifact_dir_str or None,
                    summary=summary[:500] if summary else None,
                )
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
                task_status = (
                    TaskStatus.FAILED if workflow_failure else TaskStatus.SUCCEEDED
                )
                self._tasks_store.update_task_status(
                    task_id=task_id,
                    status=task_status,
                    result=self._build_task_result_payload(
                        existing_result=existing_task_result,
                        incoming_result=result_data,
                        summary=summary[:500],
                        storage_ref=artifact_dir_str or None,
                        object_key=result_object_key,
                        execution_id=execution_id,
                        artifact_id=artifact_id,
                        landing_metadata=landing_metadata,
                        deliverable_identity=deliverable_identity,
                        acceptance_evidence=acceptance_evidence,
                    ),
                    completed_at=landed_at,
                    error=workflow_failure,
                )
                logger.info(
                    "Task updated id=%s status=%s",
                    task_id,
                    task_status.value,
                )
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

    def get_landed_result(
        self,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a previously landed result by execution_id.

        Returns a dict with status, storage_ref, summary, result_json, attachments.
        """
        return landing_readback.get_landed_result(
            artifacts_store=self._artifacts_store,
            tasks_store=self._tasks_store,
            execution_id=execution_id,
        )

"""Attachment and deliverable file helpers for task result landing."""

import os
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services.task_result_landing_core.common import clean_string


def extract_attachment_filenames(attachments_input: List[Dict[str, Any]]) -> List[str]:
    """Return unique safe attachment filenames from attachment payloads."""
    filenames: List[str] = []
    seen: set[str] = set()
    for attachment in attachments_input or []:
        if not isinstance(attachment, dict):
            continue
        safe_name = clean_string(os.path.basename(attachment.get("filename") or ""))
        if safe_name and safe_name not in seen:
            filenames.append(safe_name)
            seen.add(safe_name)
    return filenames


def derive_execution_trace_attachments(
    *,
    result_data: Dict[str, Any],
    deliverable_identity: Dict[str, Any],
    task: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Build attachment payloads from execution-trace file paths."""
    if not isinstance(result_data, dict):
        return []
    if result_data.get("attachments"):
        return []

    execution_trace = result_data.get("execution_trace")
    if not isinstance(execution_trace, dict):
        execution_trace = {}

    sandbox_roots = resolve_attachment_snapshot_roots(
        result_data=result_data,
        execution_trace=execution_trace,
    )
    if not sandbox_roots:
        return []

    desired_filenames = deliverable_filenames_from_identity(deliverable_identity)
    candidate_paths: List[str] = []
    identity_probe_paths = deliverable_probe_paths_from_identity(deliverable_identity)
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
                and not file_matches_task_window(file_path=file_path, task=task)
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


def resolve_attachment_snapshot_roots(
    *,
    result_data: Dict[str, Any],
    execution_trace: Dict[str, Any],
) -> List[pathlib.Path]:
    """Resolve existing sandbox roots that can provide attachment snapshots."""
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
        candidate = clean_string(raw_path)
        if not candidate:
            continue
        candidate_path = pathlib.Path(candidate).expanduser().resolve()
        if not candidate_path.exists() or candidate_path in seen:
            continue
        seen.add(candidate_path)
        roots.append(candidate_path)
    return roots


def deliverable_probe_paths_from_identity(
    deliverable_identity: Dict[str, Any],
) -> List[str]:
    """Return candidate relative paths implied by deliverable identity."""
    paths: List[str] = []
    seen: set[str] = set()

    def add_path(raw_value: Any) -> None:
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

    add_path(deliverable_identity.get("deliverable_path"))
    deliverable_targets = deliverable_identity.get("deliverable_targets")
    if isinstance(deliverable_targets, list):
        for target in deliverable_targets:
            if isinstance(target, dict):
                add_path(target.get("deliverable_path"))
    return paths


def coerce_utc_datetime(value: Any) -> Optional[datetime]:
    """Return a UTC-aware datetime or None."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def file_matches_task_window(
    *,
    file_path: pathlib.Path,
    task: Optional[Any],
) -> bool:
    """Return True when a candidate file belongs to the task time window."""
    if task is None:
        return True
    try:
        stat = file_path.stat()
    except OSError:
        return False

    file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    started_at = coerce_utc_datetime(
        getattr(task, "started_at", None)
    ) or coerce_utc_datetime(getattr(task, "created_at", None))

    if started_at and file_mtime < (started_at - timedelta(seconds=2)):
        return False
    return True


def deliverable_filenames_from_identity(
    deliverable_identity: Dict[str, Any],
) -> set[str]:
    """Return expected deliverable filenames from deliverable identity."""
    filenames: set[str] = set()
    deliverable_path = clean_string(deliverable_identity.get("deliverable_path"))
    if deliverable_path:
        filenames.add(os.path.basename(deliverable_path))
    deliverable_targets = deliverable_identity.get("deliverable_targets")
    if isinstance(deliverable_targets, list):
        for target in deliverable_targets:
            if not isinstance(target, dict):
                continue
            target_path = clean_string(target.get("deliverable_path"))
            if target_path:
                filenames.add(os.path.basename(target_path))
    return filenames


def expected_markdown_deliverables(
    deliverable_identity: Dict[str, Any],
) -> List[str]:
    """Return expected markdown deliverable filenames."""
    return sorted(
        filename
        for filename in deliverable_filenames_from_identity(deliverable_identity)
        if filename.lower().endswith(".md")
    )


def build_markdown_deliverable_failure(
    *,
    deliverable_identity: Dict[str, Any],
    attachment_filenames: List[str],
    result_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return a failure payload when expected markdown deliverables did not land."""
    expected_deliverables = expected_markdown_deliverables(deliverable_identity)
    if not expected_deliverables:
        return None

    landed_filenames = {
        clean_string(os.path.basename(filename))
        for filename in attachment_filenames or []
        if clean_string(os.path.basename(filename))
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
        "message": "Required markdown deliverables did not land as file-backed attachments",
        "expected_deliverables": expected_deliverables,
        "missing_deliverables": missing_deliverables,
        "attachment_filenames": list(attachment_filenames or []),
        "files_created": list(files_created) if isinstance(files_created, list) else [],
        "files_modified": list(files_modified)
        if isinstance(files_modified, list)
        else [],
    }

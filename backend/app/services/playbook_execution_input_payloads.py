"""Durable file-backed inputs for runner playbook executions.

Large execution inputs do not belong in the hot ``tasks`` JSON columns. This
module lands them in the workspace storage shared by backend and runners, and
returns a small, checksum-pinned descriptor that is safe to keep on the task.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.app.services.result_object_contract import json_payload_bytes


EXECUTION_INPUT_PAYLOAD_SCHEMA_VERSION = 1
EXECUTION_INPUT_INLINE_LIMIT_BYTES = 8 * 1024
EXECUTION_INPUT_MAX_BYTES = 8 * 1024 * 1024
EXECUTION_INPUT_DIRECTORY = "execution-inputs"
EXECUTION_INPUT_FILENAME = "inputs.json"

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


class ExecutionInputPayloadError(RuntimeError):
    """Raised when durable execution inputs cannot be safely landed or read."""


def _safe_identifier(value: Any, *, field_name: str) -> str:
    token = str(value or "").strip()
    if not token or not _SAFE_IDENTIFIER.fullmatch(token):
        raise ExecutionInputPayloadError(
            f"execution_input_{field_name}_invalid"
        )
    return token


def _default_workspace_loader(workspace_id: str) -> Any:
    from backend.app.services.stores.postgres.workspaces_store import (
        PostgresWorkspacesStore,
    )

    return PostgresWorkspacesStore().get_workspace_sync(workspace_id)


def _workspace_storage_root(
    workspace_id: str,
    *,
    workspace_loader: Optional[Callable[[str], Any]] = None,
) -> Path:
    loader = workspace_loader or _default_workspace_loader
    workspace = loader(workspace_id)
    storage_base_path = (
        getattr(workspace, "storage_base_path", None) if workspace else None
    )
    if not isinstance(storage_base_path, str) or not storage_base_path.strip():
        raise ExecutionInputPayloadError(
            "execution_input_workspace_storage_unavailable"
        )
    root = Path(storage_base_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _payload_path(root: Path, execution_id: str) -> Path:
    target = (
        root
        / EXECUTION_INPUT_DIRECTORY
        / execution_id
        / EXECUTION_INPUT_FILENAME
    ).resolve()
    if root != target and root not in target.parents:
        raise ExecutionInputPayloadError("execution_input_path_outside_workspace")
    return target


def _payload_descriptor(
    *,
    workspace_id: str,
    execution_id: str,
    payload_path: Path,
    payload_bytes: bytes,
) -> Dict[str, Any]:
    return {
        "schema_version": EXECUTION_INPUT_PAYLOAD_SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "execution_id": execution_id,
        "storage_ref": str(payload_path),
        "checksum_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "bytes": len(payload_bytes),
        "mime_type": "application/json",
    }


def land_execution_inputs(
    *,
    workspace_id: str,
    execution_id: str,
    inputs: Dict[str, Any],
    workspace_loader: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Atomically land exact runner inputs and return their durable descriptor."""

    resolved_workspace_id = _safe_identifier(
        workspace_id,
        field_name="workspace_id",
    )
    resolved_execution_id = _safe_identifier(
        execution_id,
        field_name="execution_id",
    )
    if not isinstance(inputs, dict):
        raise ExecutionInputPayloadError("execution_input_payload_not_object")

    payload_bytes = json_payload_bytes(inputs)
    if len(payload_bytes) > EXECUTION_INPUT_MAX_BYTES:
        raise ExecutionInputPayloadError("execution_input_payload_over_limit")

    root = _workspace_storage_root(
        resolved_workspace_id,
        workspace_loader=workspace_loader,
    )
    target = _payload_path(root, resolved_execution_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing_bytes = target.read_bytes()
        if existing_bytes != payload_bytes:
            raise ExecutionInputPayloadError(
                "execution_input_identity_conflict"
            )
        return _payload_descriptor(
            workspace_id=resolved_workspace_id,
            execution_id=resolved_execution_id,
            payload_path=target,
            payload_bytes=payload_bytes,
        )

    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")

    try:
        with temporary.open("xb") as file_obj:
            file_obj.write(payload_bytes)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != payload_bytes:
                raise ExecutionInputPayloadError(
                    "execution_input_identity_conflict"
                )
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()

    return _payload_descriptor(
        workspace_id=resolved_workspace_id,
        execution_id=resolved_execution_id,
        payload_path=target,
        payload_bytes=payload_bytes,
    )


def prepare_execution_input_context(
    *,
    workspace_id: str,
    execution_id: str,
    inputs: Dict[str, Any],
    workspace_loader: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Keep small inputs inline and externalize only payloads above the budget."""

    payload_bytes = json_payload_bytes(inputs)
    if len(payload_bytes) <= EXECUTION_INPUT_INLINE_LIMIT_BYTES:
        return {"inputs": dict(inputs)}
    return {
        "execution_inputs_ref": land_execution_inputs(
            workspace_id=workspace_id,
            execution_id=execution_id,
            inputs=inputs,
            workspace_loader=workspace_loader,
        )
    }


def hydrate_execution_inputs(
    execution_context: Optional[Dict[str, Any]],
    *,
    workspace_loader: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Return exact inline or checksum-verified file-backed execution inputs."""

    context = execution_context if isinstance(execution_context, dict) else {}
    inline_inputs = context.get("inputs")
    if isinstance(inline_inputs, dict) and not inline_inputs.get("_compacted"):
        return dict(inline_inputs)

    descriptor = context.get("execution_inputs_ref")
    if not isinstance(descriptor, dict):
        return {}
    if descriptor.get("schema_version") != EXECUTION_INPUT_PAYLOAD_SCHEMA_VERSION:
        raise ExecutionInputPayloadError("execution_input_schema_unsupported")

    workspace_id = _safe_identifier(
        descriptor.get("workspace_id") or context.get("workspace_id"),
        field_name="workspace_id",
    )
    execution_id = _safe_identifier(
        descriptor.get("execution_id") or context.get("execution_id"),
        field_name="execution_id",
    )
    root = _workspace_storage_root(
        workspace_id,
        workspace_loader=workspace_loader,
    )
    expected_path = _payload_path(root, execution_id)
    storage_ref = descriptor.get("storage_ref")
    if not isinstance(storage_ref, str) or Path(storage_ref).resolve() != expected_path:
        raise ExecutionInputPayloadError("execution_input_storage_ref_mismatch")

    expected_bytes = descriptor.get("bytes")
    if not isinstance(expected_bytes, int) or not 0 <= expected_bytes <= EXECUTION_INPUT_MAX_BYTES:
        raise ExecutionInputPayloadError("execution_input_size_invalid")
    payload_bytes = expected_path.read_bytes()
    if len(payload_bytes) != expected_bytes:
        raise ExecutionInputPayloadError("execution_input_size_mismatch")

    expected_checksum = descriptor.get("checksum_sha256")
    actual_checksum = hashlib.sha256(payload_bytes).hexdigest()
    if not isinstance(expected_checksum, str) or actual_checksum != expected_checksum:
        raise ExecutionInputPayloadError("execution_input_checksum_mismatch")

    try:
        payload = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionInputPayloadError("execution_input_payload_invalid_json") from exc
    if not isinstance(payload, dict):
        raise ExecutionInputPayloadError("execution_input_payload_not_object")
    return payload

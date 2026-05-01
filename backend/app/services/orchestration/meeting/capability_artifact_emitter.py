"""Generic meeting artifact emission through installed capability packs."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml

from backend.app.models.task_ir import ArtifactReference


PRODUCER_MANIFEST_FIELD = "meeting_artifact_producers"


def emit_requested_artifacts_for_task_ir(
    *,
    task_ir: Any,
    session: Optional[Any],
    workspace: Optional[Any] = None,
    decision: str,
    action_items: list[dict[str, Any]],
    action_intents: Optional[list[Any]],
) -> None:
    """Emit requested artifacts without core knowing pack-specific domains."""
    governance = _as_dict(getattr(getattr(task_ir, "metadata", None), "governance", None))
    requested_mime_types = _requested_mime_types(governance)
    producers = _resolve_artifact_producers(requested_mime_types, governance)
    if not producers:
        return

    for producer in producers:
        result = _invoke_producer(
            producer=producer,
            task_ir=task_ir,
            session=session,
            workspace=workspace,
            decision=decision,
            action_items=action_items,
            action_intents=action_intents,
            governance=governance,
        )
        _apply_producer_result(
            result=result,
            task_ir=task_ir,
            session=session,
        )


def _requested_mime_types(governance: Dict[str, Any]) -> set[str]:
    requested: set[str] = set()
    requested_output_type = str(governance.get("requested_output_type") or "").strip()
    if requested_output_type:
        requested.add(requested_output_type)

    for deliverable in list(governance.get("deliverables") or []):
        if not isinstance(deliverable, dict):
            continue
        mime_type = str(deliverable.get("mime_type") or deliverable.get("type") or "").strip()
        if mime_type:
            requested.add(mime_type)
    return requested


def _resolve_artifact_producers(
    requested_mime_types: Iterable[str],
    governance: Dict[str, Any],
) -> list[Dict[str, Any]]:
    requested = {str(mime_type or "").strip() for mime_type in requested_mime_types}
    producers: list[Dict[str, Any]] = []
    for manifest_path in _iter_capability_manifest_paths():
        manifest = _read_manifest(manifest_path)
        if not manifest:
            continue
        pack_code = str(manifest.get("code") or manifest_path.parent.name)
        for producer in list(manifest.get(PRODUCER_MANIFEST_FIELD) or []):
            if not isinstance(producer, dict):
                continue
            mime_type = str(producer.get("mime_type") or "").strip()
            backend = str(producer.get("backend") or "").strip()
            if not backend:
                continue
            if mime_type in requested or _producer_requested_by_governance(
                producer, governance
            ):
                producers.append(
                    {
                        **producer,
                        "pack_code": pack_code,
                        "manifest_path": str(manifest_path),
                    }
                )
    return producers


def _producer_requested_by_governance(
    producer: Dict[str, Any],
    governance: Dict[str, Any],
) -> bool:
    request_key = str(producer.get("governance_request_key") or "").strip()
    if not request_key:
        return False
    constraints = _as_dict(governance.get("governance_constraints"))
    request = _as_dict(constraints.get(request_key))
    return request.get("requested") is True


def _iter_capability_manifest_paths() -> list[Path]:
    app_root = Path(__file__).resolve().parents[3]
    capability_root = app_root / "capabilities"
    if not capability_root.exists():
        return []
    return sorted(capability_root.glob("*/manifest.yaml"))


def _read_manifest(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _invoke_producer(
    *,
    producer: Dict[str, Any],
    task_ir: Any,
    session: Optional[Any],
    workspace: Optional[Any],
    decision: str,
    action_items: list[dict[str, Any]],
    action_intents: Optional[list[Any]],
    governance: Dict[str, Any],
) -> Dict[str, Any]:
    backend = str(producer.get("backend") or "")
    callable_backend = _import_backend_callable(backend)
    result = callable_backend(
        task_id=str(getattr(task_ir, "task_id", "") or ""),
        workspace_id=str(getattr(task_ir, "workspace_id", "") or ""),
        session_id=str(getattr(session, "id", "") or "") if session is not None else "",
        decision=decision,
        action_items=action_items,
        action_intents=action_intents,
        governance=governance,
        session_metadata=_as_dict(getattr(session, "metadata", None)) if session is not None else {},
        workspace_metadata=_as_dict(getattr(workspace, "metadata", None)) if workspace is not None else {},
    )
    return result if isinstance(result, dict) else {}


def _import_backend_callable(backend: str) -> Any:
    module_name, separator, symbol_name = backend.partition(":")
    if not separator or not module_name or not symbol_name:
        raise RuntimeError(f"Invalid artifact producer backend: {backend}")

    _ensure_capability_import_root()
    module_candidates = [module_name]
    if module_name.startswith("capabilities."):
        module_candidates.append(f"backend.app.{module_name}")

    errors = []
    for candidate in module_candidates:
        try:
            module = importlib.import_module(candidate)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        symbol = getattr(module, symbol_name, None)
        if callable(symbol):
            return symbol
        errors.append(f"{candidate}: missing callable {symbol_name}")
    raise RuntimeError(f"Unable to import artifact producer {backend}: {'; '.join(errors)}")


def _ensure_capability_import_root() -> None:
    app_root = Path(__file__).resolve().parents[3]
    app_root_str = str(app_root)
    if app_root_str not in sys.path:
        sys.path.insert(0, app_root_str)


def _apply_producer_result(
    *,
    result: Dict[str, Any],
    task_ir: Any,
    session: Optional[Any],
) -> None:
    status = result.get("status")
    if status not in {"compiled", "emitted", "ok", "success"}:
        return

    artifact = _artifact_reference_from_payload(result.get("artifact"))
    if artifact is not None:
        task_ir.artifacts.append(artifact)

    if session is None:
        return
    if getattr(session, "metadata", None) is None:
        session.metadata = {}

    session_updates = _as_dict(result.get("session_metadata_updates"))
    for key, value in session_updates.items():
        if key and value not in (None, "", [], {}):
            session.metadata[str(key)] = value

    workspace_updates = _as_dict(result.get("workspace_metadata_updates"))
    if workspace_updates:
        pending = _as_dict(session.metadata.get("capability_workspace_metadata_updates"))
        for key, value in workspace_updates.items():
            if key and value not in (None, "", [], {}):
                pending[str(key)] = value
        session.metadata["capability_workspace_metadata_updates"] = pending


def _artifact_reference_from_payload(raw: Any) -> Optional[ArtifactReference]:
    if not isinstance(raw, dict):
        return None
    artifact_id = str(raw.get("id") or "").strip()
    artifact_type = str(raw.get("type") or "").strip()
    source = str(raw.get("source") or "capability").strip()
    uri = str(raw.get("uri") or "").strip()
    if not (artifact_id and artifact_type and uri):
        return None
    return ArtifactReference(
        id=artifact_id,
        type=artifact_type,
        source=source,
        uri=uri,
        metadata=_as_dict(raw.get("metadata")) or None,
    )


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


__all__ = ["emit_requested_artifacts_for_task_ir"]

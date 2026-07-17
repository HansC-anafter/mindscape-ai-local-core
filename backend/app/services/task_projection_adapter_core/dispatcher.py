"""Dispatch task identity writes to one validated pack-owned adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from backend.app.services.capability_backend_loader import (
    resolve_capability_backend_callable,
)

from .models import ALLOWED_PROJECTION_REASONS
from .registry import resolve_definition


def _task_value(task: Any, field: str) -> Any:
    if isinstance(task, dict):
        return task.get(field)
    return getattr(task, field, None)


def project_task_identity(*, conn, task: Any, reason: str) -> bool:
    """Write a pack identity projection in the caller's existing transaction."""

    normalized_reason = str(reason)
    if normalized_reason not in ALLOWED_PROJECTION_REASONS:
        raise ValueError(f"task_projection_adapter_invalid_reason:{normalized_reason}")
    definition = resolve_definition(str(_task_value(task, "pack_id") or ""))
    if definition is None:
        return False
    target = definition.callable_override or resolve_capability_backend_callable(
        backend_path=definition.backend_path,
        capability_dir=definition.capability_dir,
    )
    result = target(conn=conn, task=task, reason=normalized_reason)
    if result is False:
        raise RuntimeError(
            f"task_projection_adapter_write_rejected:{definition.capability_code}"
        )
    return True


def build_task_display_inputs(*, task: Any) -> dict[str, Any]:
    """Ask the owning pack for one bounded opaque run-log input envelope."""

    definition = resolve_definition(str(_task_value(task, "pack_id") or ""))
    if definition is None:
        return {}
    if (
        definition.display_callable_override is None
        and not definition.display_backend_path.strip()
    ):
        return {}
    target = (
        definition.display_callable_override
        or resolve_capability_backend_callable(
            backend_path=definition.display_backend_path,
            capability_dir=definition.capability_dir,
        )
    )
    payload = target(task=task)
    if not isinstance(payload, Mapping):
        raise RuntimeError(
            f"task_projection_display_payload_invalid:{definition.capability_code}"
        )
    return _validated_display_payload(definition.capability_code, payload)


def _validated_display_payload(
    capability_code: str,
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RuntimeError(
            f"task_projection_display_payload_invalid:{capability_code}"
        )
    normalized = dict(payload)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"task_projection_display_payload_not_json:{capability_code}"
        ) from exc
    if len(encoded) > 4096:
        raise RuntimeError(
            f"task_projection_display_payload_over_budget:{capability_code}"
        )
    return normalized


def load_task_display_input_overlays(*, conn, rows) -> dict[str, dict[str, Any]]:
    """Bulk-dispatch exact selected task IDs to each owning pack reader."""

    grouped: dict[str, tuple[Any, list[Any]]] = {}
    for row in rows:
        definition = resolve_definition(str(_task_value(row, "pack_id") or ""))
        if definition is None:
            continue
        if (
            definition.display_bulk_callable_override is None
            and not definition.display_bulk_backend_path.strip()
        ):
            continue
        current = grouped.get(definition.capability_code)
        if current is None:
            grouped[definition.capability_code] = (definition, [row])
        else:
            current[1].append(row)

    overlays: dict[str, dict[str, Any]] = {}
    for definition, owned_rows in grouped.values():
        target = (
            definition.display_bulk_callable_override
            or resolve_capability_backend_callable(
                backend_path=definition.display_bulk_backend_path,
                capability_dir=definition.capability_dir,
            )
        )
        payload = target(conn=conn, rows=owned_rows)
        if not isinstance(payload, Mapping):
            raise RuntimeError(
                f"task_projection_display_bulk_invalid:{definition.capability_code}"
            )
        requested_ids = {
            str(_task_value(row, "task_id") or "").strip()
            for row in owned_rows
        }
        for raw_task_id, raw_overlay in payload.items():
            task_id = str(raw_task_id or "").strip()
            if not task_id or task_id not in requested_ids:
                raise RuntimeError(
                    f"task_projection_display_bulk_unrequested_id:{definition.capability_code}"
                )
            overlays[task_id] = _validated_display_payload(
                definition.capability_code,
                raw_overlay,
            )
    return overlays

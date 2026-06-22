"""Shared tool and capability availability explanation helpers."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_tool_availability_explanation(
    *,
    tool_id: str | None,
    workspace_id: str | None,
    source: str,
    reason: str,
    workspace_binding_applied: bool = False,
    rank: int | None = None,
) -> dict[str, Any]:
    return {
        "tool_id": _text(tool_id),
        "available": True,
        "source": source,
        "reason": reason,
        "workspace_id": _text(workspace_id),
        "workspace_binding_applied": bool(workspace_binding_applied),
        "rank": rank,
    }


def attach_tool_availability_explanations(
    results: Iterable[Mapping[str, Any]],
    *,
    workspace_id: str | None,
    source: str,
    reason: str,
    workspace_binding_applied: bool = False,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        payload = dict(result)
        payload["availability_explanation"] = build_tool_availability_explanation(
            tool_id=_text(payload.get("tool_id")),
            workspace_id=workspace_id,
            source=source,
            reason=reason,
            workspace_binding_applied=workspace_binding_applied,
            rank=index,
        )
        enriched.append(payload)
    return enriched


def build_capability_api_activation_explanation(
    *,
    capability_code: str,
    status: str,
    reason: str,
    expected_routes: Iterable[tuple[str, str]] | None = None,
    conflicts: Iterable[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "capability_code": capability_code,
        "status": status,
        "reason": reason,
        "expected_routes": [
            {"method": method, "path": path}
            for method, path in sorted(expected_routes or [])
        ],
        "conflicts": [
            {"method": method, "path": path}
            for method, path in sorted(conflicts or [])
        ],
    }

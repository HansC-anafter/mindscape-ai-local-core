"""Public bounded tool-dispatch contract for installed capability packs."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

try:  # Installed packs import the public ``app`` namespace.
    from app.services.capability_registry import call_tool_async as _call_tool_async
except ModuleNotFoundError:  # Source tests import through ``backend.app``.
    from backend.app.services.capability_registry import (
        call_tool_async as _call_tool_async,
    )


TOOL_ARGUMENTS_MAX_BYTES = 64 * 1024
_TOOL_FQN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def _normalize_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, Mapping):
        raise ValueError("capability_tool_dispatch_arguments_object_required")
    try:
        encoded = json.dumps(
            dict(arguments),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("capability_tool_dispatch_arguments_json_required") from exc
    if len(encoded) > TOOL_ARGUMENTS_MAX_BYTES:
        raise ValueError("capability_tool_dispatch_arguments_too_large")
    return json.loads(encoded)


async def dispatch_capability_tool(
    tool_fqn: str,
    arguments: Mapping[str, Any],
) -> Any:
    """Invoke one registered capability tool without owning retry or durability."""

    normalized_fqn = str(tool_fqn or "").strip()
    if not _TOOL_FQN.fullmatch(normalized_fqn):
        raise ValueError("capability_tool_dispatch_fqn_invalid")
    capability_code, tool_code = normalized_fqn.split(".", 1)
    normalized_arguments = _normalize_arguments(arguments)
    return await _call_tool_async(
        capability_code,
        tool_code,
        **normalized_arguments,
    )


__all__ = [
    "TOOL_ARGUMENTS_MAX_BYTES",
    "dispatch_capability_tool",
]

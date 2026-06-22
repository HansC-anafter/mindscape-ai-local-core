"""Default local browser queue semantics."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .task_family_registry import (
    DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION,
    is_managed_browser_batch_task,
    resolve_managed_browser_batch_queue_override,
)

LEGACY_DEFAULT_LOCAL_QUEUE_PARTITION = "default_local"
LEGACY_DEFAULT_QUEUE_PARTITION = "default"


def _clean_token(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    token = value.strip()
    return token or None


def _mapping_value(mapping: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        token = _clean_token(mapping.get(key))
        if token:
            return token
    return None


def _context_playbook_code(execution_context: Any) -> Optional[str]:
    if not isinstance(execution_context, Mapping):
        return None
    return _mapping_value(execution_context, "playbook_code", "pack_id")


def is_default_local_browser_playbook(
    pack_id: Any,
    playbook_code: Any = None,
) -> bool:
    """Return true when the playbook is owned by the batch browser lane."""
    context = {}
    playbook_token = _clean_token(playbook_code)
    if playbook_token:
        context["playbook_code"] = playbook_token
    return is_managed_browser_batch_task(pack_id, context)


def is_default_local_browser_legacy_partition(value: Any) -> bool:
    """Return true only for the canonical batch browser queue."""
    return _clean_token(value) == DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION


def resolve_default_local_browser_queue_override(
    pack_id: Any,
    execution_context: Any = None,
) -> Optional[str]:
    """
    Resolve queue overrides required by the default-local-browser product contract.

    Batch browser playbooks always route to the canonical batch browser queue.
    Non-batch default-local work remains on the general default queue.
    """
    return resolve_managed_browser_batch_queue_override(pack_id, execution_context)

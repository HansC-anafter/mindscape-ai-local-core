"""
Shared resolver for runner-relevant metadata extracted from playbook specs.

Single source of truth — used by both playbook_execution.py and
playbook_rerun.py to ensure consistent task context creation.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource class constants
# ---------------------------------------------------------------------------

RESOURCE_CLASS_BROWSER = "browser"
RESOURCE_CLASS_COMPUTE = "compute"
RESOURCE_CLASS_API = "api"

VALID_RESOURCE_CLASSES = {
    RESOURCE_CLASS_BROWSER,
    RESOURCE_CLASS_COMPUTE,
    RESOURCE_CLASS_API,
}

# Conservative default — unknown playbooks should NOT flood the api pool.
DEFAULT_RESOURCE_CLASS = RESOURCE_CLASS_COMPUTE


def resolve_runner_metadata(playbook_run) -> Dict[str, Any]:
    """Extract all runner-relevant metadata from a PlaybookRun.

    Returns a dict with optional keys:
      - concurrency: dict  (lock_key_input, max_parallel, lock_scope)
      - runner_timeout_seconds: int
      - lifecycle_hooks: dict
      - resource_class: str  ("browser" | "compute" | "api")
      - queue_shard: str
      - capability_code: str

    Both playbook_execution.py and playbook_rerun.py must call this
    function so that task.execution_context always contains the same
    set of runner fields.
    """
    meta: Dict[str, Any] = {}

    if playbook_run is None:
        meta["resource_class"] = DEFAULT_RESOURCE_CLASS
        return meta

    pj = getattr(playbook_run, "playbook_json", None)

    # --- capability_code ---
    pb = getattr(playbook_run, "playbook", None)
    if pb and getattr(pb, "metadata", None):
        cap_code = getattr(pb.metadata, "capability_code", None)
        if cap_code:
            meta["capability_code"] = cap_code

    if pj is None:
        meta["resource_class"] = DEFAULT_RESOURCE_CLASS
        return meta

    # --- concurrency ---
    concurrency = getattr(pj, "concurrency", None)
    if concurrency:
        meta["concurrency"] = {
            "lock_key_input": concurrency.lock_key_input,
            "max_parallel": concurrency.max_parallel,
            "lock_scope": concurrency.lock_scope,
        }

    # --- runner_timeout_seconds ---
    ep = getattr(pj, "execution_profile", None) or {}
    if isinstance(ep, dict):
        raw_timeout = ep.get("runner_timeout_seconds")
        if isinstance(raw_timeout, (int, float)) and raw_timeout > 0:
            max_ceiling = int(
                os.environ.get("LOCAL_CORE_RUNNER_MAX_TIMEOUT_SECONDS", "43200")
            )
            meta["runner_timeout_seconds"] = min(int(raw_timeout), max_ceiling)

    # --- lifecycle_hooks ---
    lifecycle_hooks = getattr(pj, "lifecycle_hooks", None)
    if lifecycle_hooks:
        meta["lifecycle_hooks"] = lifecycle_hooks

    # --- resource_class ---
    meta["resource_class"] = _resolve_resource_class_from_profile(ep)
    queue_shard = _resolve_queue_shard_from_profile(ep)
    if queue_shard:
        meta["queue_shard"] = queue_shard

    return meta


def should_route_through_runner(
    playbook_run,
    requested_backend: Optional[str],
    env_execution_mode: Optional[str],
) -> bool:
    """Decide whether a workflow should use runner dispatch.

    ``auto`` normally follows ``LOCAL_CORE_EXECUTION_MODE``. However, if a
    playbook declares runner-only metadata such as concurrency locks,
    lifecycle hooks, or long-running browser timeouts, we must route it
    through the runner queue so those controls can take effect.
    """
    backend = (requested_backend or "auto").strip().lower()
    env_mode = (env_execution_mode or "in_process").strip().lower()
    runner_meta = resolve_runner_metadata(playbook_run)
    requires_runner = _has_runner_only_metadata(runner_meta)

    if backend == "runner":
        return True
    if backend == "remote":
        return False
    if backend == "in_process":
        return requires_runner

    if backend != "auto":
        return env_mode == "runner"

    if requires_runner:
        return True

    return env_mode == "runner"


def _has_runner_only_metadata(runner_meta: Dict[str, Any]) -> bool:
    """Detect metadata that only works correctly when dispatched via runner."""
    if not isinstance(runner_meta, dict):
        return False

    if runner_meta.get("concurrency"):
        return True

    if runner_meta.get("lifecycle_hooks"):
        return True

    timeout = runner_meta.get("runner_timeout_seconds")
    if isinstance(timeout, int) and timeout > 0:
        return True

    resource_class = runner_meta.get("resource_class")
    if isinstance(resource_class, str) and resource_class in {
        RESOURCE_CLASS_BROWSER,
        RESOURCE_CLASS_API,
    }:
        return True

    return False


def _resolve_resource_class_from_profile(ep: Optional[Dict[str, Any]]) -> str:
    """Determine resource_class from execution_profile dict.

    Priority:
      1. Explicit ``resource_class`` field in spec  (new field)
      2. Heuristic: ``runner_timeout_seconds > 3600`` → browser
      3. Default → compute (conservative)
    """
    if not isinstance(ep, dict):
        return DEFAULT_RESOURCE_CLASS

    # 1. Explicit declaration (preferred)
    declared = ep.get("resource_class")
    if isinstance(declared, str) and declared in VALID_RESOURCE_CLASSES:
        return declared

    # 2. Heuristic: long timeout → likely browser automation
    raw_timeout = ep.get("runner_timeout_seconds")
    if isinstance(raw_timeout, (int, float)) and raw_timeout > 3600:
        return RESOURCE_CLASS_BROWSER

    # 3. Conservative default
    return DEFAULT_RESOURCE_CLASS


def _resolve_queue_shard_from_profile(ep: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return explicit queue_shard from execution_profile when declared."""
    if not isinstance(ep, dict):
        return None

    declared = ep.get("queue_shard")
    if isinstance(declared, str):
        normalized = declared.strip()
        if normalized:
            return normalized
    return None


def resolve_resource_class_from_task(task) -> str:
    """Resolve resource_class for an already-created Task object.

    Used by the runner dispatch loop.  Checks task.execution_context
    for a pre-set resource_class (set at create time by
    resolve_runner_metadata).  Falls back to DEFAULT_RESOURCE_CLASS.
    """
    ctx = getattr(task, "execution_context", None)
    if isinstance(ctx, dict):
        rc = ctx.get("resource_class")
        if isinstance(rc, str) and rc in VALID_RESOURCE_CLASSES:
            return rc
    return DEFAULT_RESOURCE_CLASS

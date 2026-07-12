"""Pure IG browser workload envelope classification."""

from __future__ import annotations

import hashlib
import json
from typing import Any


CLASSIFIER_VERSION = 1
APPROVED_ENVELOPES = {
    "ig_analyze_following": {
        "workload_code": "ig_analyze_following",
        "partition": "browser_local",
        "profile_locked": True,
    },
    "ig_batch_pin_references.browser": {
        "workload_code": "ig_batch_pin_references",
        "partition": "browser_local",
        "profile_locked": True,
    },
    "ig_batch_pin_references.captured_posts": {
        "workload_code": "ig_batch_pin_references",
        "partition": "default_local_browser",
        "profile_locked": False,
    },
    "ig_pin_post_detail": {
        "workload_code": "ig_pin_post_detail",
        "partition": "browser_local",
        "profile_locked": True,
    },
}
BROWSER_LOCAL_ALIASES = {"browser_local", "ig_browser"}


def canonical_input_hash(inputs: dict[str, Any]) -> str:
    encoded = json.dumps(inputs, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def classify_task_envelope(task: dict[str, Any]) -> dict[str, Any]:
    context = _mapping(task.get("execution_context"))
    params = _mapping(task.get("params"))
    inputs = _mapping(context.get("inputs")) or _mapping(task.get("inputs")) or params
    admission = _mapping(context.get("resource_admission"))
    requirements = _mapping(context.get("resource_requirements")) or _mapping(
        admission.get("requirements")
    )
    workload_code = str(
        context.get("playbook_code") or task.get("pack_id") or task.get("workload_code") or ""
    ).strip()
    source_mode = str(inputs.get("source_mode") or "").strip().lower()

    if workload_code == "ig_analyze_following":
        envelope_id = "ig_analyze_following"
    elif workload_code == "ig_pin_post_detail":
        envelope_id = "ig_pin_post_detail"
    elif workload_code == "ig_batch_pin_references" and source_mode == "browser":
        envelope_id = "ig_batch_pin_references.browser"
    elif workload_code == "ig_batch_pin_references" and source_mode == "captured_posts":
        envelope_id = "ig_batch_pin_references.captured_posts"
    else:
        queue_shard = str(task.get("queue_shard") or context.get("queue_shard") or "").strip()
        partition = (
            "browser_local"
            if queue_shard in BROWSER_LOCAL_ALIASES
            else queue_shard
        )
        return {
            "valid": False,
            "failures": ["unapproved_browser_envelope"],
            "envelope_id": "",
            "workload_code": workload_code,
            "partition": partition,
            "inputs": inputs,
            "payload_sha256": canonical_input_hash(inputs),
        }

    contract = APPROVED_ENVELOPES[envelope_id]
    queue_shard = str(task.get("queue_shard") or context.get("queue_shard") or "").strip()
    concurrency_key = str(task.get("concurrency_key") or "").strip()
    user_data_dir = str(inputs.get("user_data_dir") or "").strip()
    profile_lock = requirements.get("ig_profile_lock")
    failures: list[str] = []

    if contract["partition"] == "browser_local":
        if queue_shard not in BROWSER_LOCAL_ALIASES:
            failures.append("browser_local_partition_mismatch")
        if not user_data_dir:
            failures.append("profile_identity_missing")
        if profile_lock is False or profile_lock in (None, ""):
            failures.append("profile_lock_missing")
    else:
        if queue_shard != "default_local_browser":
            failures.append("captured_partition_mismatch")
        if profile_lock is not False:
            failures.append("captured_profile_lock_not_cleared")
        target_handle = str(inputs.get("target_handle") or "").strip()
        if not target_handle:
            failures.append("captured_target_missing")
        if not concurrency_key.startswith("concurrency:ig_batch_pin_target:"):
            failures.append("captured_target_concurrency_mismatch")

    return {
        "valid": not failures,
        "failures": failures,
        "classifier_version": CLASSIFIER_VERSION,
        "envelope_id": envelope_id,
        "workload_code": workload_code,
        "partition": contract["partition"],
        "inputs": inputs,
        "payload_sha256": canonical_input_hash(inputs),
    }


__all__ = [
    "APPROVED_ENVELOPES",
    "CLASSIFIER_VERSION",
    "canonical_input_hash",
    "classify_task_envelope",
]

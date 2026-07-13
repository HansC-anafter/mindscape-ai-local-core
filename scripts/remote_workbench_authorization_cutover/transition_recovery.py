"""Early closure and exact recovery for interrupted runtime policy transitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io import CutoverError, assert_private_file
from .policy_receipt import (
    RECEIPT_NAME,
    policy_transition_state,
    record_policy_intent,
)
from .secure_inputs import SecureInputs, require_access_token_remaining


ORIGINAL_POLICY_NAME = "runtime-policy-before.json"
CHECKPOINT_NAME = "authorization-enrollment-checkpoint.json"
_CLOSURE_ARTIFACTS = (RECEIPT_NAME, ORIGINAL_POLICY_NAME, CHECKPOINT_NAME)


def transition_artifacts_present(directory: Path) -> bool:
    """Detect durable transition ownership without reading artifact contents."""

    return any(
        path.exists() or path.is_symlink()
        for path in (directory / name for name in _CLOSURE_ARTIFACTS)
    )


def safe_close_before_preflight(directory: Path, runtime: Any) -> bool:
    """Close public transport before repository or runtime preflight on rerun."""

    if not transition_artifacts_present(directory):
        return False
    runtime.safe_close("authorization_interrupted_transition_preflight")
    return True


def load_original_policy(directory: Path) -> dict[str, Any]:
    """Load the exact receipt-bound policy baseline from private evidence."""

    path = directory / ORIGINAL_POLICY_NAME
    assert_private_file(path, max_bytes=32_768)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Saved initial runtime policy is malformed") from error
    if not isinstance(payload, dict) or type(payload.get("revision")) is not int:
        raise CutoverError("Saved initial runtime policy identity is invalid")
    return payload


def recover_uncheckpointed_transition(
    *,
    inputs: SecureInputs,
    runtime: Any,
    target_workspace_id: str,
) -> dict[str, Any]:
    """Restore one exact orphaned policy projection while the tunnel is closed."""

    original = load_original_policy(inputs.directory)
    current = runtime.get_runtime_policy()
    state = policy_transition_state(
        inputs.directory,
        original=original,
        current=current,
    )
    if state in {"original", "restored"}:
        return original

    revision = current.get("revision")
    if type(revision) is not int:
        raise CutoverError("Interrupted policy readback revision is invalid")
    require_access_token_remaining(inputs)
    body = runtime.policy_body(original, revision)
    record_policy_intent(inputs.directory, original=original, body=body)
    restored = runtime.transition(
        body,
        assertion_path=inputs.jwt_paths["hans"],
        workspace_id=target_workspace_id,
        reopen=False,
    )
    if policy_transition_state(
        inputs.directory,
        original=original,
        current=restored,
    ) != "restored":
        raise CutoverError("Interrupted policy rollback did not restore the baseline")
    return original

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.policy_receipt import (
    current_policy_requires_rollback,
    record_policy_intent,
)


def _policy(revision: int, state: str = "enrollment_only") -> dict:
    return {
        "revision": revision,
        "access_issuer": None if revision == 7 else "https://issuer.example",
        "access_audience": None if revision == 7 else "audience",
        "remote_access_state": state,
        "local_core_super_admins": [],
    }


def test_policy_receipt_allows_original_noop_or_exact_runner_projection_only(
    tmp_path: Path,
) -> None:
    original = _policy(7)
    body = {
        **_policy(8),
        "expected_revision": 7,
    }
    body.pop("revision")
    record_policy_intent(tmp_path, original=original, body=body)

    assert current_policy_requires_rollback(
        tmp_path,
        original=original,
        current=original,
    ) is False
    assert current_policy_requires_rollback(
        tmp_path,
        original=original,
        current=_policy(8),
    ) is True

    divergent = _policy(9, state="enforced")
    with pytest.raises(CutoverError, match="Concurrent runtime policy divergence"):
        current_policy_requires_rollback(
            tmp_path,
            original=original,
            current=divergent,
        )


def test_policy_receipt_preserves_prior_owned_projection_after_later_put_timeout(
    tmp_path: Path,
) -> None:
    original = _policy(7)
    first = {**_policy(8), "expected_revision": 7}
    first.pop("revision")
    second = {**_policy(9, state="enforced"), "expected_revision": 8}
    second.pop("revision")
    record_policy_intent(tmp_path, original=original, body=first)
    record_policy_intent(tmp_path, original=original, body=second)

    assert current_policy_requires_rollback(
        tmp_path,
        original=original,
        current=_policy(8),
    ) is True


def test_policy_receipt_recognizes_exact_owned_restore_after_rollback_timeout(
    tmp_path: Path,
) -> None:
    original = _policy(7)
    pending = {**_policy(8), "expected_revision": 7}
    pending.pop("revision")
    restored = {**_policy(9), "expected_revision": 8}
    restored.pop("revision")
    restored["access_issuer"] = None
    restored["access_audience"] = None
    record_policy_intent(tmp_path, original=original, body=pending)
    record_policy_intent(tmp_path, original=original, body=restored)

    assert current_policy_requires_rollback(
        tmp_path,
        original=original,
        current={**original, "revision": 9},
    ) is False

import hashlib
import json
from pathlib import Path

import pytest

from backend.app.services.artifact_disclosure import policy_profile


def _policy_paths():
    directory = (
        Path(policy_profile.__file__).resolve().parent / "policies"
    )
    return directory / "share.v1.json", directory / "share.v1.sha256"


def test_share_policy_bytes_match_the_committed_lock():
    policy_path, lock_path = _policy_paths()
    expected = lock_path.read_text(encoding="ascii").strip()
    actual = hashlib.sha256(policy_path.read_bytes()).hexdigest()

    assert actual == expected
    assert policy_profile.load_share_policy_profile().ref.content_sha256 == (
        expected
    )


def test_policy_schema_rejects_unknown_fields_and_unbounded_values():
    policy_path, _ = _policy_paths()
    payload = json.loads(policy_path.read_text(encoding="utf-8"))

    with pytest.raises(
        ValueError,
        match="disclosure_policy_fields_invalid",
    ):
        policy_profile._validate_profile_payload(
            {**payload, "runtime_fallback": True}
        )

    payload["max_findings_per_item"] = 1001
    with pytest.raises(
        ValueError,
        match="disclosure_policy_finding_bound_invalid",
    ):
        policy_profile._validate_profile_payload(payload)

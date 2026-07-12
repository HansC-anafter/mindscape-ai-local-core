from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CommandExecutor, CutoverError
from remote_workbench_authorization_cutover.resources import (
    RedisResourceSampler,
    ResourceSnapshot,
)
from remote_workbench_authorization_cutover.secure_inputs import (
    EXPECTED_AUDIENCE,
    EXPECTED_INHERITANCE_WORKSPACE_ID,
    EXPECTED_ISSUER,
    EXPECTED_TARGET_WORKSPACE_ID,
    MIN_ACCESS_TOKEN_REMAINING_SECONDS,
    load_secure_inputs,
)


def _segment(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _assertion(email: str, subject: str, **claim_overrides) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "kid": "fixture-key"}
    claims = {
        "iss": EXPECTED_ISSUER,
        "aud": [EXPECTED_AUDIENCE],
        "type": "app",
        "sub": subject,
        "email": email,
        "iat": now - 30,
        "nbf": now - 30,
        "exp": now + MIN_ACCESS_TOKEN_REMAINING_SECONDS + 600,
    }
    claims.update(claim_overrides)
    return f"{_segment(header)}.{_segment(claims)}.fixture-signature"


def _secure_dir(tmp_path: Path, *, revision: int = 7) -> Path:
    directory = tmp_path / "secure"
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    policy = {
        "expected_revision": revision,
        "access_issuer": EXPECTED_ISSUER,
        "access_audience": EXPECTED_AUDIENCE,
        "remote_access_state": "enforced",
        "local_core_super_admins": [
            {"email": "hans@anafter.co", "subject": "subject-hans", "status": "active"},
            {
                "email": "pproo.reader@gmail.com",
                "subject": "subject-pproo",
                "status": "active",
            },
        ],
    }
    files = {
        "runtime-policy-next.json": json.dumps(policy),
        "hans.jwt": _assertion("hans@anafter.co", "subject-hans"),
        "pproo.jwt": _assertion("pproo.reader@gmail.com", "subject-pproo"),
        "outsider.jwt": _assertion("outsider@example.com", "subject-outsider"),
        "cloudflare-account-id.txt": "a" * 32,
        "cloudflare-tunnel-id.txt": "11111111-2222-4333-8444-555555555555",
        "cloudflare-api-token.txt": "fixture-cloudflare-read-write-token",
    }
    for name, value in files.items():
        path = directory / name
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
    return directory


def test_secure_inputs_require_locked_config_and_three_distinct_principals(tmp_path: Path) -> None:
    inputs = load_secure_inputs(_secure_dir(tmp_path))

    assert inputs.policy["expected_revision"] == 7
    assert inputs.policy["access_issuer"] == EXPECTED_ISSUER
    assert inputs.policy["access_audience"] == EXPECTED_AUDIENCE
    assert inputs.jwt_claims["hans"]["sub"] == "subject-hans"
    assert inputs.jwt_claims["outsider"]["sub"] == "subject-outsider"


def test_secure_inputs_reject_group_readable_secret(tmp_path: Path) -> None:
    directory = _secure_dir(tmp_path)
    os.chmod(directory / "hans.jwt", 0o640)

    with pytest.raises(CutoverError, match="Invalid permissions"):
        load_secure_inputs(directory)


def test_secure_inputs_reject_unlocked_policy_shape(tmp_path: Path) -> None:
    directory = _secure_dir(tmp_path)
    policy_path = directory / "runtime-policy-next.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["access_issuer"] = "https://wrong.example.com"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    os.chmod(policy_path, 0o600)

    with pytest.raises(CutoverError, match="locked rollout"):
        load_secure_inputs(directory)


def test_secure_inputs_reject_boolean_revision_and_boolean_or_inverted_times(
    tmp_path: Path,
) -> None:
    directory = _secure_dir(tmp_path)
    policy_path = directory / "runtime-policy-next.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["expected_revision"] = True
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    os.chmod(policy_path, 0o600)
    with pytest.raises(CutoverError, match="expected_revision"):
        load_secure_inputs(directory)

    policy["expected_revision"] = 7
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    os.chmod(policy_path, 0o600)
    token_path = directory / "hans.jwt"
    token_path.write_text(
        _assertion("hans@anafter.co", "subject-hans", nbf=True),
        encoding="utf-8",
    )
    os.chmod(token_path, 0o600)
    with pytest.raises(CutoverError, match="missing nbf"):
        load_secure_inputs(directory)

    now = int(time.time())
    token_path.write_text(
        _assertion(
            "hans@anafter.co",
            "subject-hans",
            nbf=now + MIN_ACCESS_TOKEN_REMAINING_SECONDS + 800,
            exp=now + MIN_ACCESS_TOKEN_REMAINING_SECONDS + 700,
        ),
        encoding="utf-8",
    )
    os.chmod(token_path, 0o600)
    with pytest.raises(CutoverError, match="time claims"):
        load_secure_inputs(directory)


def test_secure_inputs_reject_symlinks_and_oversized_files(tmp_path: Path) -> None:
    directory = _secure_dir(tmp_path)
    linked_directory = tmp_path / "secure-link"
    linked_directory.symlink_to(directory, target_is_directory=True)
    with pytest.raises(CutoverError, match="symbolic link"):
        load_secure_inputs(linked_directory)

    hans_path = directory / "hans.jwt"
    original = hans_path.read_text(encoding="utf-8")
    source = tmp_path / "hans-source.jwt"
    source.write_text(original, encoding="utf-8")
    os.chmod(source, 0o600)
    hans_path.unlink()
    hans_path.symlink_to(source)
    with pytest.raises(CutoverError, match="Symbolic links"):
        load_secure_inputs(directory)

    hans_path.unlink()
    hans_path.write_text("x" * 16_385, encoding="utf-8")
    os.chmod(hans_path, 0o600)
    with pytest.raises(CutoverError, match="size limit"):
        load_secure_inputs(directory)


def test_secure_inputs_require_distinct_admin_subjects_and_outsider_email(
    tmp_path: Path,
) -> None:
    directory = _secure_dir(tmp_path)
    policy_path = directory / "runtime-policy-next.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["local_core_super_admins"][1]["subject"] = "subject-hans"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    os.chmod(policy_path, 0o600)
    with pytest.raises(CutoverError, match="unique"):
        load_secure_inputs(directory)

    policy["local_core_super_admins"][1]["subject"] = "subject-pproo"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    os.chmod(policy_path, 0o600)
    outsider_path = directory / "outsider.jwt"
    outsider_path.write_text(_assertion("", "subject-outsider"), encoding="utf-8")
    os.chmod(outsider_path, 0o600)
    with pytest.raises(CutoverError, match="non-empty email"):
        load_secure_inputs(directory)


class FakeExecutor:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[list[str]] = []

    def run(self, args, *, timeout_seconds=60.0, input_text=None) -> str:
        self.calls.append(list(args))
        return json.dumps(self.payload)


def _redis_payload() -> dict:
    return {
        "totals": {"pending": 4, "processing": 3, "delayed": 2, "deadletter": 1},
        "inventory": [
            "mindscape:queue:deadletter:default|list",
            "mindscape:queue:delayed:default|zset",
            "mindscape:queue:pending:default|list",
            "mindscape:queue:processing:default|zset",
        ],
        "runners": {"count": 2, "capacity": 6, "inflight": 1, "malformed": 0},
    }


def test_direct_redis_snapshot_covers_four_types_inventory_and_runner_capacity(
    tmp_path: Path,
) -> None:
    executor = FakeExecutor(_redis_payload())
    sampler = RedisResourceSampler(executor)

    snapshot = sampler.capture()
    sampler.persist(snapshot, tmp_path, "06a-infra-before")

    assert snapshot.totals == {
        "pending": 4,
        "processing": 3,
        "delayed": 2,
        "deadletter": 1,
    }
    assert snapshot.runners == {"count": 2, "capacity": 6, "inflight": 1}
    command = executor.calls[0]
    assert command[:5] == [
        "docker",
        "exec",
        "mindscape-ai-local-core-redis",
        "redis-cli",
        "--raw",
    ]
    assert "LLEN" in command[-2]
    assert "ZCARD" in command[-2]
    assert (
        tmp_path / "queue-inventory-06a-infra-before.txt"
    ).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "label",
    ["before", "../../escape", "phase06-unknown-before", "06a-infra-during"],
)
def test_real_resource_sampler_rejects_labels_outside_window_contract(
    tmp_path: Path,
    label: str,
) -> None:
    with pytest.raises(CutoverError, match="Phase06 contract"):
        RedisResourceSampler.persist(
            RedisResourceSampler._validate(_redis_payload()),
            tmp_path,
            label,
        )


@pytest.mark.parametrize("drift", ["pending", "processing", "delayed", "deadletter"])
def test_resource_compare_rejects_each_queue_type_delta(drift: str) -> None:
    before = RedisResourceSampler._validate(_redis_payload())
    changed = _redis_payload()
    changed["totals"][drift] += 1
    after = RedisResourceSampler._validate(changed)

    with pytest.raises(CutoverError, match="queue totals"):
        RedisResourceSampler.compare(before, after)


def test_resource_compare_rejects_new_key_and_runner_change() -> None:
    before = RedisResourceSampler._validate(_redis_payload())
    new_key = _redis_payload()
    new_key["inventory"].append("mindscape:queue:temp:new|list")
    with pytest.raises(CutoverError, match="key/type inventory"):
        RedisResourceSampler.compare(before, RedisResourceSampler._validate(new_key))

    runner_change = _redis_payload()
    runner_change["runners"]["capacity"] += 1
    with pytest.raises(CutoverError, match="runner count or capacity"):
        RedisResourceSampler.compare(before, RedisResourceSampler._validate(runner_change))

    inflight_change = _redis_payload()
    inflight_change["runners"]["inflight"] += 1
    RedisResourceSampler.compare(before, RedisResourceSampler._validate(inflight_change))


def test_command_failure_never_echoes_sensitive_arguments() -> None:
    secret = "secret-assertion-value"
    with pytest.raises(CutoverError) as captured:
        CommandExecutor().run(
            [sys.executable, "-c", "raise SystemExit(9)", secret],
            timeout_seconds=5.0,
        )
    assert secret not in str(captured.value)

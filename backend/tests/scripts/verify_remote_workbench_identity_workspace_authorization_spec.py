from __future__ import annotations

import base64
import json
import os
import sys
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

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
    load_remote_ingress_inputs,
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


def _ingress_secure_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "ingress-secure"
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    files = {
        "cloudflare-account-id.txt": "a" * 32,
        "cloudflare-tunnel-id.txt": "11111111-2222-4333-8444-555555555555",
        "cloudflare-api-token.txt": "fixture-cloudflare-read-write-token",
    }
    for name, value in files.items():
        path = directory / name
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
    return directory


def _runner_module():
    path = REPO_ROOT / "scripts/verify_remote_workbench_identity_workspace_authorization.py"
    spec = spec_from_file_location("remote_workbench_authorization_runner", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_remote_ingress_inputs_require_only_three_private_cloudflare_files(
    tmp_path: Path,
) -> None:
    directory = _ingress_secure_dir(tmp_path)

    inputs = load_remote_ingress_inputs(directory)

    assert inputs.policy == {}
    assert inputs.jwt_paths == {}
    assert inputs.cloudflare_account_id == "a" * 32
    assert inputs.cloudflare_tunnel_id == "11111111-2222-4333-8444-555555555555"
    with pytest.raises(CutoverError):
        load_secure_inputs(directory)


def test_remote_ingress_inputs_reject_unsafe_token_and_directory_links(
    tmp_path: Path,
) -> None:
    directory = _ingress_secure_dir(tmp_path)
    os.chmod(directory / "cloudflare-api-token.txt", 0o640)
    with pytest.raises(CutoverError, match="Invalid permissions"):
        load_remote_ingress_inputs(directory)

    linked = tmp_path / "ingress-link"
    linked.symlink_to(directory, target_is_directory=True)
    with pytest.raises(CutoverError, match="symbolic link"):
        load_remote_ingress_inputs(linked)


def test_runner_parser_keeps_full_actions_strict_and_ingress_recovery_narrow(
    tmp_path: Path,
) -> None:
    runner = _runner_module()
    secure = _ingress_secure_dir(tmp_path)

    recovered = runner.build_parser().parse_args(
        ["recover-ingress", "--secure-input-dir", str(secure)]
    )

    assert recovered.action == "recover-ingress"
    assert recovered.secure_input_dir == secure
    with pytest.raises(SystemExit):
        runner.build_parser().parse_args(
            ["cutover", "--secure-input-dir", str(secure)]
        )


def test_runner_ingress_recovery_does_not_construct_runtime_or_release_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _runner_module()
    secure = _ingress_secure_dir(tmp_path)
    inputs = load_remote_ingress_inputs(secure)

    class FakeIngressGate:
        def __init__(self, _http) -> None:
            pass

        def recover_exact(self, received):
            assert received == inputs
            return {"status": "succeeded", "tunnel_id": inputs.cloudflare_tunnel_id}

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Ingress recovery constructed an unrelated gate")

    monkeypatch.setattr(runner, "load_remote_ingress_inputs", lambda _path: inputs)
    monkeypatch.setattr(runner, "RemoteIngressGate", FakeIngressGate)
    monkeypatch.setattr(runner, "HttpClient", lambda: object())
    for name in (
        "CommandExecutor",
        "RuntimeGate",
        "RedisResourceSampler",
        "CutoverWorkflow",
        "lock_phase06_repositories",
    ):
        monkeypatch.setattr(runner, name, forbidden)

    result = runner._run_locked(
        SimpleNamespace(action="recover-ingress", secure_input_dir=secure)
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "status": "succeeded",
        "tunnel_id": "11111111-2222-4333-8444-555555555555",
    }


def test_secure_inputs_require_locked_config_and_three_distinct_principals(
    tmp_path: Path,
) -> None:
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


def _closed_redis_payload() -> dict:
    payload = _redis_payload()
    payload["totals"]["processing"] = 0
    payload["runners"]["inflight"] = 0
    return payload


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
    before = RedisResourceSampler._validate(_closed_redis_payload())
    changed = _closed_redis_payload()
    changed["totals"][drift] += 1
    after = RedisResourceSampler._validate(changed)

    with pytest.raises(CutoverError, match="queue totals|zero processing"):
        RedisResourceSampler.compare(before, after)


def test_resource_compare_rejects_new_key_and_runner_change() -> None:
    before = RedisResourceSampler._validate(_closed_redis_payload())
    new_key = _closed_redis_payload()
    new_key["inventory"].append("mindscape:queue:temp:new|list")
    with pytest.raises(CutoverError, match="key/type inventory"):
        RedisResourceSampler.compare(before, RedisResourceSampler._validate(new_key))

    runner_change = _closed_redis_payload()
    runner_change["runners"]["capacity"] += 1
    with pytest.raises(CutoverError, match="runner count or capacity"):
        RedisResourceSampler.compare(
            before, RedisResourceSampler._validate(runner_change)
        )

    inflight_change = _closed_redis_payload()
    inflight_change["runners"]["inflight"] += 1
    with pytest.raises(CutoverError, match="zero processing and runner inflight"):
        RedisResourceSampler.compare(
            before,
            RedisResourceSampler._validate(inflight_change),
        )


def test_resource_compare_requires_zero_processing_even_without_delta() -> None:
    before = RedisResourceSampler._validate(_redis_payload())
    after = RedisResourceSampler._validate(_redis_payload())

    with pytest.raises(CutoverError, match="zero processing and runner inflight"):
        RedisResourceSampler.compare(before, after)


def test_command_failure_never_echoes_sensitive_arguments() -> None:
    secret = "secret-assertion-value"
    with pytest.raises(CutoverError) as captured:
        CommandExecutor().run(
            [sys.executable, "-c", "raise SystemExit(9)", secret],
            timeout_seconds=5.0,
        )
    assert secret not in str(captured.value)

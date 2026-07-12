from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.http import HttpResponse
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.enrollment_checkpoint import ingress_identity
from remote_workbench_authorization_cutover.remote_ingress import (
    CANONICAL_CONFIG,
    RemoteIngressGate,
    canonical_config_sha256,
)
from remote_workbench_authorization_cutover.secure_inputs import SecureInputs
from remote_workbench_remote_ingress_lock import load_lock


ACCOUNT_ID = "a" * 32
TUNNEL_ID = "11111111-2222-4333-8444-555555555555"
EXPECTED_HASH = "9fe62f75ad018e404b2146f7d8462ec8fc72a52e535c3fab8f7d9b5a67ac9948"


def _inputs(tmp_path: Path) -> SecureInputs:
    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    os.chmod(secure, 0o700)
    token = secure / "cloudflare-api-token.txt"
    token.write_text("fixture-cloudflare-read-write-token", encoding="utf-8")
    os.chmod(token, 0o600)
    return SecureInputs(
        directory=secure,
        policy={},
        jwt_paths={},
        jwt_claims={},
        cloudflare_account_id=ACCOUNT_ID,
        cloudflare_tunnel_id=TUNNEL_ID,
        cloudflare_api_token_path=token,
    )


def _envelope(result: dict) -> HttpResponse:
    return HttpResponse(
        200,
        {},
        json.dumps({"success": True, "result": result}).encode("utf-8"),
    )


def _configuration(version: int, config: dict | None = None) -> dict:
    return {
        "account_id": ACCOUNT_ID,
        "tunnel_id": TUNNEL_ID,
        "version": version,
        "config": config if config is not None else CANONICAL_CONFIG,
    }


class CloudflareHttp:
    def __init__(self, *, readback_config: dict | None = None) -> None:
        self.calls: list[dict] = []
        self.readback_config = readback_config or CANONICAL_CONFIG
        self.config_gets = 0

    def request(self, method, url, **kwargs) -> HttpResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")
        if method == "GET" and not url.endswith("/configurations"):
            return _envelope(
                {
                    "id": TUNNEL_ID,
                    "account_tag": ACCOUNT_ID,
                    "config_src": "cloudflare",
                }
            )
        if method == "PUT":
            assert kwargs["payload"] == {"config": CANONICAL_CONFIG}
            return _envelope(_configuration(5, self.readback_config))
        self.config_gets += 1
        version = 4 if self.config_gets == 1 else 5
        return _envelope(_configuration(version, self.readback_config))


def test_apply_exact_writes_launcher_loadable_lock_from_full_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path)
    state = tmp_path / "state"
    monkeypatch.setenv("REMOTE_WORKBENCH_BRIDGE_STATE_DIR", str(state))
    gate = RemoteIngressGate(
        CloudflareHttp(),
        now=lambda: datetime(2026, 7, 13, 5, 6, 7, 123456, tzinfo=timezone.utc),
    )

    before = gate.capture_prechange(inputs)
    written = gate.apply_exact(inputs)
    loaded = load_lock(state / "remote-ingress-lock.json")

    assert before["config_src"] == "cloudflare"
    assert canonical_config_sha256() == EXPECTED_HASH
    assert written["config_sha256"] == EXPECTED_HASH
    assert loaded.config_sha256 == EXPECTED_HASH
    assert loaded.config_version == 5
    assert loaded.tunnel_id == TUNNEL_ID
    assert state.stat().st_mode & 0o777 == 0o700
    assert (state / "remote-ingress-lock.json").stat().st_mode & 0o777 == 0o600


def test_remote_ingress_rejects_local_config_source_and_extra_config(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    local = CloudflareHttp()
    original = local.request

    def local_source(method, url, **kwargs):
        if method == "GET" and not url.endswith("/configurations"):
            return _envelope(
                {"id": TUNNEL_ID, "account_tag": ACCOUNT_ID, "config_src": "local"}
            )
        return original(method, url, **kwargs)

    local.request = local_source
    with pytest.raises(CutoverError, match="remotely-managed"):
        RemoteIngressGate(local).capture_prechange(inputs)

    extra = {**CANONICAL_CONFIG, "originRequest": {}}
    with pytest.raises(CutoverError, match="canonical config"):
        RemoteIngressGate(CloudflareHttp(readback_config=extra)).apply_exact(inputs)


def test_resume_verifies_exact_ingress_and_locks_without_a_second_put(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path)
    state = tmp_path / "resume-state"
    monkeypatch.setenv("REMOTE_WORKBENCH_BRIDGE_STATE_DIR", str(state))
    http = CloudflareHttp()
    gate = RemoteIngressGate(http)
    gate.capture_prechange(inputs)
    expected = ingress_identity(gate.apply_exact(inputs))
    puts_before = sum(call["method"] == "PUT" for call in http.calls)

    assert gate.verify_exact(inputs, expected)["config_version"] == 5
    assert sum(call["method"] == "PUT" for call in http.calls) == puts_before == 1

    changed = dict(expected)
    changed["config_version"] = 6
    with pytest.raises(CutoverError, match="checkpoint no longer matches"):
        gate.verify_exact(inputs, changed)


def test_workflow_applies_remote_ingress_only_after_pending_runtime_coherence() -> None:
    source = (
        REPO_ROOT / "scripts/remote_workbench_authorization_cutover/workflow.py"
    ).read_text(encoding="utf-8")
    package = source.index("self.release.package_current()")
    install = source.index("self.release.install_current", package)
    pending = source.index("pending_readback = self.runtime.transition", install)
    pending_closed = source.index("reopen=False", pending)
    coherent = source.index("self.runtime.verify_pending_coherence", pending_closed)
    ingress = source.index("self.ingress.apply_exact(inputs)", coherent)
    reopen = source.index("self.runtime.reopen_transport()", ingress)
    enrollment = source.index("self.runtime.verify_enrollment_assertions", reopen)

    assert package < install < pending < pending_closed < coherent
    assert coherent < ingress < reopen < enrollment

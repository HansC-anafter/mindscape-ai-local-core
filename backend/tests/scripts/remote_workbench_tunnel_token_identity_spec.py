from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_remote_ingress_lock import (
    IngressLock,
    IngressLockError,
    canonical_config_sha256,
    live_projection,
    load_token_tunnel_id,
    verify_token_identity,
)


TUNNEL_A = "11111111-2222-4333-8444-555555555555"
TUNNEL_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _lock(tunnel_id: str = TUNNEL_A) -> IngressLock:
    return IngressLock(
        schema_version=1,
        tunnel_id=tunnel_id,
        config_version=17,
        config_sha256=canonical_config_sha256(),
        config_src="cloudflare",
        hostname="remote-workbench.mindscapeai.app",
        service="http://mindscape-ai-local-core-frontend:3001",
        catch_all="http_status:404",
        verified_at="2026-07-13T08:29:59.123456Z",
    )


def _write_token(tmp_path: Path, decoded: bytes) -> Path:
    path = tmp_path / "tunnel-token"
    path.write_text(base64.b64encode(decoded).decode("ascii") + "\n", encoding="ascii")
    os.chmod(path, 0o600)
    return path


def _token_payload(tunnel_uuid: str = TUNNEL_A, **extra: object) -> bytes:
    payload: dict[str, object] = {
        "a": "account-tag",
        "s": base64.b64encode(b"fixture-secret").decode("ascii"),
        "t": tunnel_uuid,
    }
    payload.update(extra)
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def test_secure_token_decoder_returns_only_the_exact_tunnel_uuid(tmp_path: Path) -> None:
    token_path = _write_token(tmp_path, _token_payload())

    assert load_token_tunnel_id(token_path) == TUNNEL_A
    assert verify_token_identity(_lock(), token_path) == TUNNEL_A


def test_same_config_version_cannot_mask_a_wrong_token_tunnel(tmp_path: Path) -> None:
    lock = _lock()
    assert live_projection(lock, 17)["remote_ingress_verified"] is True
    token_path = _write_token(tmp_path, _token_payload(TUNNEL_B))

    with pytest.raises(IngressLockError, match="tunnel_token_identity_mismatch"):
        verify_token_identity(lock, token_path)


@pytest.mark.parametrize(
    "decoded",
    [
        b"not-json",
        json.dumps({"a": "account", "s": "c2VjcmV0"}).encode("utf-8"),
        json.dumps(
            {"a": "account", "s": "c2VjcmV0", "t": [TUNNEL_A, TUNNEL_B]}
        ).encode("utf-8"),
        _token_payload(TUNNEL_A, tunnel_id=TUNNEL_B),
    ],
)
def test_malformed_or_aliased_token_identity_fails_closed(
    tmp_path: Path,
    decoded: bytes,
) -> None:
    token_path = _write_token(tmp_path, decoded)

    with pytest.raises(IngressLockError, match="tunnel_token_(malformed|schema_mismatch)"):
        load_token_tunnel_id(token_path)


def test_duplicate_tunnel_identity_field_is_rejected(tmp_path: Path) -> None:
    secret = base64.b64encode(b"fixture-secret").decode("ascii")
    decoded = (
        f'{{"a":"account","s":"{secret}","t":"{TUNNEL_A}",'
        f'"t":"{TUNNEL_B}"}}'
    ).encode("utf-8")

    with pytest.raises(IngressLockError, match="tunnel_token_duplicate_field"):
        load_token_tunnel_id(_write_token(tmp_path, decoded))


def test_non_base64_or_insecure_token_file_is_rejected(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed-token"
    malformed.write_text("%%%not-base64%%%\n", encoding="ascii")
    os.chmod(malformed, 0o600)
    with pytest.raises(IngressLockError, match="tunnel_token_malformed"):
        load_token_tunnel_id(malformed)

    target = _write_token(tmp_path, _token_payload())
    link = tmp_path / "token-link"
    link.symlink_to(target)
    with pytest.raises(IngressLockError, match="tunnel_token_not_regular"):
        load_token_tunnel_id(link)

    os.chmod(target, 0o644)
    with pytest.raises(IngressLockError, match="tunnel_token_mode_mismatch"):
        load_token_tunnel_id(target)


def test_token_failure_never_includes_secret_content(tmp_path: Path) -> None:
    marker = "never-log-this-token-secret"
    payload = {
        "a": "account",
        "s": base64.b64encode(marker.encode("utf-8")).decode("ascii"),
        "t": TUNNEL_B,
    }
    token_path = _write_token(
        tmp_path,
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )

    with pytest.raises(IngressLockError) as captured:
        verify_token_identity(_lock(), token_path)
    assert marker not in str(captured.value)

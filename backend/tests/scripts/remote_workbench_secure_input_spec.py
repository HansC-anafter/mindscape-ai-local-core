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

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.secure_inputs import (
    EXPECTED_AUDIENCE,
    EXPECTED_ISSUER,
    MIN_ACCESS_TOKEN_REMAINING_SECONDS,
    load_secure_inputs,
)


def _segment(payload: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")


def _assertion(*, email: str, subject: str) -> str:
    now = int(time.time())
    return ".".join(
        (
            _segment({"alg": "RS256", "kid": "test-key"}),
            _segment(
                {
                    "iss": EXPECTED_ISSUER,
                    "aud": [EXPECTED_AUDIENCE],
                    "type": "app",
                    "email": email,
                    "sub": subject,
                    "iat": now - 10,
                    "nbf": now - 10,
                    "exp": now + MIN_ACCESS_TOKEN_REMAINING_SECONDS + 600,
                }
            ),
            "signature",
        )
    )


def _secure_fixture(tmp_path: Path) -> Path:
    secure = tmp_path / "secure-inputs"
    secure.mkdir(mode=0o700)
    policy = {
        "expected_revision": 7,
        "access_issuer": EXPECTED_ISSUER,
        "access_audience": EXPECTED_AUDIENCE,
        "remote_access_state": "enforced",
        "local_core_super_admins": [
            {
                "email": "hans@anafter.co",
                "subject": "subject-hans",
                "status": "active",
            },
            {
                "email": "pproo.reader@gmail.com",
                "subject": "subject-pproo",
                "status": "active",
            },
        ],
    }
    files = {
        "runtime-policy-next.json": json.dumps(policy),
        "hans.jwt": _assertion(
            email="hans@anafter.co",
            subject="subject-hans",
        ),
        "pproo.jwt": _assertion(
            email="pproo.reader@gmail.com",
            subject="subject-pproo",
        ),
        "cloudflare-account-id.txt": "a" * 32,
        "cloudflare-tunnel-id.txt": "11111111-2222-4333-8444-555555555555",
        "cloudflare-api-token.txt": "cloudflare-api-token-value",
    }
    for name, value in files.items():
        path = secure / name
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
    return secure


def test_runtime_policy_input_is_bounded_before_json_read(tmp_path: Path) -> None:
    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    os.chmod(secure, 0o700)
    policy = secure / "runtime-policy-next.json"
    policy.write_text("x" * 32_769, encoding="utf-8")
    os.chmod(policy, 0o600)

    with pytest.raises(CutoverError, match="size limit"):
        load_secure_inputs(secure)


def test_initial_secure_inputs_require_two_distinct_admins_but_not_outsider(
    tmp_path: Path,
) -> None:
    secure = _secure_fixture(tmp_path)

    inputs = load_secure_inputs(secure)

    assert tuple(inputs.jwt_paths) == ("hans", "pproo")
    assert inputs.jwt_claims["hans"]["sub"] != inputs.jwt_claims["pproo"]["sub"]

    (secure / "pproo.jwt").write_text(
        (secure / "hans.jwt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(CutoverError, match="distinct principals"):
        load_secure_inputs(secure)


def test_optional_outsider_is_strictly_validated_when_present(tmp_path: Path) -> None:
    secure = _secure_fixture(tmp_path)
    outsider = secure / "outsider.jwt"
    outsider.write_text("malformed", encoding="utf-8")
    outsider.chmod(0o600)

    with pytest.raises(CutoverError, match="malformed"):
        load_secure_inputs(secure)

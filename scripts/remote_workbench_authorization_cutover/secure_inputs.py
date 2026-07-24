"""Strict validation for Remote Workbench cutover inputs."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from .io import CutoverError, assert_private_directory, assert_private_file


RUNTIME_POLICY_ID = "remote-workbench-runtime"
EXPECTED_ISSUER = "https://shy-resonance-542b.cloudflareaccess.com"
EXPECTED_AUDIENCE = (
    "94cce07bfe76d9b3903ee15316df231bb6b0c004e0a68114b8e965b2710e8b1f"
)
EXPECTED_FINGERPRINT = (
    "76be8177018ba0784dba95deb74fa344b127482ebaa500de91276840733b8c07"
)
EXPECTED_ADMIN_EMAILS = ("hans@anafter.co", "pproo.reader@gmail.com")
EXPECTED_TARGET_WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"
EXPECTED_INHERITANCE_WORKSPACE_ID = "e81713b4-385e-4755-96d5-1ceca4ec9e99"
EXPECTED_TARGET_CAPABILITIES = (
    "dance_motion_coach",
    "ig",
    "live_interface_interpreter",
    "makeup_practice_coach",
    "social_video_refs",
    "yogacoach",
)
POLICY_KEYS = {
    "expected_revision",
    "access_issuer",
    "access_audience",
    "remote_access_state",
    "local_core_super_admins",
}
ADMIN_KEYS = {"subject", "email", "status"}
BACKUP_BUDGET_SECONDS = 1_800
PACKAGE_BUDGET_SECONDS = 600
INSTALL_POLL_BUDGET_SECONDS = 600
CUTOVER_BUDGET_SECONDS = 1_800
BACKOUT_BUDGET_SECONDS = 1_200
TOKEN_SAFETY_BUDGET_SECONDS = 300
MIN_ACCESS_TOKEN_REMAINING_SECONDS = (
    BACKUP_BUDGET_SECONDS
    + PACKAGE_BUDGET_SECONDS
    + INSTALL_POLL_BUDGET_SECONDS
    + CUTOVER_BUDGET_SECONDS
    + BACKOUT_BUDGET_SECONDS
    + TOKEN_SAFETY_BUDGET_SECONDS
)
MIN_PUBLIC_OPERATION_REMAINING_SECONDS = (
    BACKOUT_BUDGET_SECONDS + TOKEN_SAFETY_BUDGET_SECONDS
)
_ACCOUNT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


@dataclass(frozen=True)
class SecureInputs:
    """Validated policy and assertion paths without token contents."""

    directory: Path
    policy: dict[str, Any]
    jwt_paths: dict[str, Path]
    jwt_claims: dict[str, dict[str, Any]]
    cloudflare_account_id: str = ""
    cloudflare_tunnel_id: str = ""
    cloudflare_api_token_path: Path | None = None


def _decode_segment(value: str) -> dict[str, Any]:
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding)
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CutoverError("Access assertion payload is malformed") from error
    if not isinstance(payload, dict):
        raise CutoverError("Access assertion payload must be an object")
    return payload


def _read_assertion(path: Path) -> tuple[str, dict[str, Any]]:
    assert_private_file(path, max_bytes=16_384)
    token = path.read_text(encoding="utf-8").strip()
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise CutoverError(f"Access assertion is malformed: {path.name}")
    header = _decode_segment(parts[0])
    claims = _decode_segment(parts[1])
    if header.get("alg") != "RS256" or not str(header.get("kid") or "").strip():
        raise CutoverError(f"Access assertion header is not RS256: {path.name}")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    now = int(time.time())
    if claims.get("iss") != EXPECTED_ISSUER or audiences != [EXPECTED_AUDIENCE]:
        raise CutoverError(f"Access assertion issuer or audience mismatch: {path.name}")
    if claims.get("type") != "app" or not str(claims.get("sub") or "").strip():
        raise CutoverError(f"Access assertion principal claims are invalid: {path.name}")
    for field in ("exp", "nbf", "iat"):
        if type(claims.get(field)) is not int:
            raise CutoverError(f"Access assertion is missing {field}: {path.name}")
    if (
        claims["exp"] - now < MIN_ACCESS_TOKEN_REMAINING_SECONDS
        or claims["nbf"] > now + 60
        or claims["iat"] > now + 60
        or claims["nbf"] > claims["exp"]
        or claims["iat"] > claims["exp"]
    ):
        raise CutoverError(f"Access assertion time claims are invalid: {path.name}")
    return hashlib.sha256(token.encode("utf-8")).hexdigest(), claims


def _validate_policy(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != POLICY_KEYS:
        raise CutoverError("runtime-policy-next.json does not match the locked schema")
    if type(payload["expected_revision"]) is not int or payload["expected_revision"] < 0:
        raise CutoverError("expected_revision must be a non-negative integer")
    if payload["access_issuer"] != EXPECTED_ISSUER:
        raise CutoverError("access_issuer does not match the locked rollout value")
    if payload["access_audience"] != EXPECTED_AUDIENCE:
        raise CutoverError("access_audience does not match the locked rollout value")
    fingerprint = hashlib.sha256(
        f"{payload['access_issuer']}\n{payload['access_audience']}".encode("utf-8")
    ).hexdigest()
    if fingerprint != EXPECTED_FINGERPRINT:
        raise CutoverError("Locked auth configuration fingerprint mismatch")
    if payload["remote_access_state"] != "enforced":
        raise CutoverError("The cutover policy must request enforced state")
    admins = payload["local_core_super_admins"]
    if not isinstance(admins, list) or len(admins) != 2:
        raise CutoverError("Exactly two Local Core super administrators are required")
    by_email: dict[str, dict[str, Any]] = {}
    seen_subjects: set[str] = set()
    for admin in admins:
        if not isinstance(admin, dict) or set(admin) != ADMIN_KEYS:
            raise CutoverError("Administrator entries do not match the locked schema")
        email = str(admin.get("email") or "").strip().lower()
        subject = str(admin.get("subject") or "").strip()
        if admin.get("status") != "active" or not subject:
            raise CutoverError("Administrators must have operator-approved active subjects")
        if (
            subject == "pending_identity_resolution"
            or email in by_email
            or subject in seen_subjects
        ):
            raise CutoverError("Administrator subjects must be unique and non-placeholder")
        by_email[email] = {"email": email, "subject": subject, "status": "active"}
        seen_subjects.add(subject)
    if tuple(sorted(by_email)) != tuple(sorted(EXPECTED_ADMIN_EMAILS)):
        raise CutoverError("Administrator emails do not match the locked rollout accounts")
    normalized = dict(payload)
    normalized["local_core_super_admins"] = [by_email[email] for email in EXPECTED_ADMIN_EMAILS]
    return normalized


def _normalize_secure_directory(directory: Path) -> Path:
    """Resolve and validate the private input directory without following a link."""

    expanded = directory.expanduser()
    if expanded.is_symlink():
        raise CutoverError("Secure input directory must not be a symbolic link")
    directory = Path(os.path.abspath(expanded))
    assert_private_directory(directory)
    return directory


def _load_cloudflare_inputs(directory: Path) -> tuple[str, str, Path]:
    account_path = directory / "cloudflare-account-id.txt"
    tunnel_path = directory / "cloudflare-tunnel-id.txt"
    api_token_path = directory / "cloudflare-api-token.txt"
    assert_private_file(account_path, max_bytes=64)
    assert_private_file(tunnel_path, max_bytes=64)
    assert_private_file(api_token_path, max_bytes=4_096)
    account_id = account_path.read_text(encoding="utf-8").strip()
    raw_tunnel_id = tunnel_path.read_text(encoding="utf-8").strip()
    api_token = api_token_path.read_text(encoding="utf-8").strip()
    if not _ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise CutoverError("Cloudflare account id is invalid")
    try:
        tunnel_id = str(UUID(raw_tunnel_id))
    except ValueError as error:
        raise CutoverError("Cloudflare tunnel id is invalid") from error
    if raw_tunnel_id != tunnel_id:
        raise CutoverError("Cloudflare tunnel id must use canonical lowercase UUID form")
    if len(api_token) < 20 or any(character.isspace() for character in api_token):
        raise CutoverError("Cloudflare API token is malformed")
    return account_id, tunnel_id, api_token_path


def load_remote_ingress_inputs(directory: Path) -> SecureInputs:
    """Load only the private Cloudflare inputs required for ingress recovery."""

    directory = _normalize_secure_directory(directory)
    account_id, tunnel_id, api_token_path = _load_cloudflare_inputs(directory)
    return SecureInputs(
        directory=directory,
        policy={},
        jwt_paths={},
        jwt_claims={},
        cloudflare_account_id=account_id,
        cloudflare_tunnel_id=tunnel_id,
        cloudflare_api_token_path=api_token_path,
    )


def load_secure_inputs(directory: Path) -> SecureInputs:
    """Load the locked policy, two admins, and an optional outsider assertion."""

    directory = _normalize_secure_directory(directory)
    policy_path = directory / "runtime-policy-next.json"
    assert_private_file(policy_path, max_bytes=32_768)
    try:
        policy = _validate_policy(json.loads(policy_path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise CutoverError("runtime-policy-next.json is malformed") from error

    jwt_paths = {
        "hans": directory / "hans.jwt",
        "pproo": directory / "pproo.jwt",
    }
    outsider_path = directory / "outsider.jwt"
    if outsider_path.exists() or outsider_path.is_symlink():
        jwt_paths["outsider"] = outsider_path
    jwt_claims: dict[str, dict[str, Any]] = {}
    token_hashes: set[str] = set()
    for label, path in jwt_paths.items():
        token_hash, claims = _read_assertion(path)
        token_hashes.add(token_hash)
        jwt_claims[label] = claims
    if len(token_hashes) != len(jwt_paths):
        raise CutoverError("Access assertions must belong to distinct principals")

    expected = {
        "hans": "hans@anafter.co",
        "pproo": "pproo.reader@gmail.com",
    }
    admins = {item["email"]: item["subject"] for item in policy["local_core_super_admins"]}
    for label, email in expected.items():
        claims = jwt_claims[label]
        if str(claims.get("email") or "").strip().lower() != email:
            raise CutoverError(f"Access assertion email mismatch: {label}")
        if str(claims.get("sub") or "").strip() != admins[email]:
            raise CutoverError(f"Access assertion subject mismatch: {label}")
    outsider = jwt_claims.get("outsider")
    if outsider is not None:
        outsider_email = str(outsider.get("email") or "").strip().lower()
        outsider_subject = str(outsider.get("sub") or "").strip()
        if not outsider_email or not outsider_subject:
            raise CutoverError(
                "Outsider assertion must include a non-empty email and subject"
            )
        if outsider_email in EXPECTED_ADMIN_EMAILS:
            raise CutoverError(
                "Outsider assertion must not use a designated administrator email"
            )
        if outsider_subject in admins.values():
            raise CutoverError("Outsider assertion must not reuse an administrator subject")

    account_id, tunnel_id, api_token_path = _load_cloudflare_inputs(directory)
    return SecureInputs(
        directory=directory,
        policy=policy,
        jwt_paths=jwt_paths,
        jwt_claims=jwt_claims,
        cloudflare_account_id=account_id,
        cloudflare_tunnel_id=tunnel_id,
        cloudflare_api_token_path=api_token_path,
    )


def require_access_token_remaining(
    inputs: SecureInputs,
    minimum_seconds: int = MIN_PUBLIC_OPERATION_REMAINING_SECONDS,
) -> None:
    """Recheck every assertion before a public transition or matrix."""

    now = int(time.time())
    for label, claims in inputs.jwt_claims.items():
        expiration = claims.get("exp")
        if type(expiration) is not int or expiration - now < minimum_seconds:
            raise CutoverError(
                f"Access assertion lifetime is insufficient for operation: {label}"
            )

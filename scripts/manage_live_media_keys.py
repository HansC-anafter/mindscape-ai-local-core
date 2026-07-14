#!/usr/bin/env python3
"""Generate fail-closed Local Core media signing material and public JWKS."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _validate_key_id(key_id: str) -> str:
    normalized = key_id.strip()
    if not normalized or not normalized.replace("-", "").replace("_", "").isalnum():
        raise ValueError("live_media_key_id_invalid")
    return normalized


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, byteorder="big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _load_private_key(path: Path):
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise ValueError("live_media_private_key_must_be_rsa_2048")
    if path.stat().st_mode & 0o077:
        raise PermissionError("live_media_private_key_permissions_invalid")
    return key


def _jwks(private_key, *, key_id: str) -> dict[str, list[dict[str, str]]]:
    numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": key_id,
                "n": _base64url_uint(numbers.n),
                "e": _base64url_uint(numbers.e),
            }
        ]
    }


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        if temporary.exists():
            temporary.unlink()


def generate(private_key_path: Path, jwks_path: Path, key_id: str) -> None:
    key_id = _validate_key_id(key_id)
    if private_key_path.exists() or jwks_path.exists():
        raise FileExistsError("live_media_key_material_already_exists")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_payload = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    jwks_payload = (
        json.dumps(_jwks(private_key, key_id=key_id), sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write(private_key_path, private_payload, mode=0o600)
    try:
        _atomic_write(jwks_path, jwks_payload, mode=0o644)
    except Exception:
        private_key_path.unlink(missing_ok=True)
        raise


def export(private_key_path: Path, jwks_path: Path, key_id: str) -> None:
    key_id = _validate_key_id(key_id)
    private_key = _load_private_key(private_key_path)
    payload = (
        json.dumps(_jwks(private_key, key_id=key_id), sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write(jwks_path, payload, mode=0o644)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("generate", "export"))
    parser.add_argument("--private-key-path", required=True, type=Path)
    parser.add_argument("--jwks-path", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()
    if args.action == "generate":
        generate(args.private_key_path, args.jwks_path, args.key_id)
    else:
        export(args.private_key_path, args.jwks_path, args.key_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

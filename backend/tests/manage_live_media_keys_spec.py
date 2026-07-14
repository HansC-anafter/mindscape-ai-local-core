from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

import pytest


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "manage_live_media_keys.py"
    spec = importlib.util.spec_from_file_location("manage_live_media_keys", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_writes_private_key_and_public_jwks_with_strict_modes(tmp_path: Path) -> None:
    module = _load_module()
    private_key_path = tmp_path / "private" / "media.pem"
    jwks_path = tmp_path / "public" / "jwks.json"

    module.generate(private_key_path, jwks_path, "media-2026-07")

    assert stat.S_IMODE(private_key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(jwks_path.stat().st_mode) == 0o644
    key = json.loads(jwks_path.read_text(encoding="utf-8"))["keys"][0]
    assert key["kid"] == "media-2026-07"
    assert {name: key[name] for name in ("kty", "use", "alg")} == {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
    }
    assert "PRIVATE" in private_key_path.read_text(encoding="utf-8")


def test_generate_refuses_to_overwrite_existing_key_material(tmp_path: Path) -> None:
    module = _load_module()
    private_key_path = tmp_path / "media.pem"
    jwks_path = tmp_path / "jwks.json"
    module.generate(private_key_path, jwks_path, "media-test")

    with pytest.raises(FileExistsError, match="live_media_key_material_already_exists"):
        module.generate(private_key_path, jwks_path, "media-test")


def test_export_refuses_unsafe_private_key_permissions(tmp_path: Path) -> None:
    module = _load_module()
    private_key_path = tmp_path / "media.pem"
    source_jwks_path = tmp_path / "source-jwks.json"
    module.generate(private_key_path, source_jwks_path, "media-test")
    private_key_path.chmod(0o640)

    with pytest.raises(PermissionError, match="live_media_private_key_permissions_invalid"):
        module.export(private_key_path, tmp_path / "exported.json", "media-test")


def test_key_id_is_bounded_to_filename_safe_characters(tmp_path: Path) -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="live_media_key_id_invalid"):
        module.generate(tmp_path / "media.pem", tmp_path / "jwks.json", "bad/key")

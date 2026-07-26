"""Fail-closed installation of compiled capability UI localization assets."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..install_result import InstallResult
from ..runtime_assets_installer_support import _sha256_integrity

LOCALIZATION_CONTRACT = "mindscape-capability-ui-localization-v1"
COMPILED_FORMAT = "formatjs-icu-messageformat-ast-v1"
COMPILER = "@formatjs/icu-messageformat-parser@3.5.15"
SUPPORTED_LOCALES = ("en", "zh-TW", "ja")
MAX_COMPILED_CATALOG_BYTES = 128 * 1024


def _fail(result: InstallResult, message: str) -> None:
    result.add_error(f"Capability UI localization is invalid: {message}")


def _safe_source_asset(source_ui_dist_dir: Path, asset_path: str) -> Path:
    source_root = source_ui_dist_dir.resolve()
    source_asset = (source_root / asset_path).resolve()
    try:
        source_asset.relative_to(source_root)
    except ValueError as exc:
        raise ValueError(f"unsafe catalog asset path: {asset_path}") from exc
    return source_asset


def install_ui_localization_assets(
    *,
    source_ui_dist_dir: Path,
    target_assets_dir: Path,
    capability_code: str,
    version_segment: str,
    localization: Any,
    result: InstallResult,
) -> dict[str, Any] | None:
    """Copy one exact three-locale descriptor into the versioned UI asset lane."""
    if not isinstance(localization, dict):
        _fail(result, "ui_dist_manifest.json has no localization descriptor")
        return None

    expected_scalars = {
        "contract": LOCALIZATION_CONTRACT,
        "namespace": capability_code,
        "source_locale": "en",
        "fallback_locale": "en",
        "format": COMPILED_FORMAT,
        "compiler": COMPILER,
    }
    for key, expected in expected_scalars.items():
        if localization.get(key) != expected:
            _fail(result, f"{key} must equal {expected}")
            return None

    if localization.get("supported_locales") != list(SUPPORTED_LOCALES):
        _fail(result, "supported_locales must be [en, zh-TW, ja]")
        return None

    keyset_sha256 = localization.get("keyset_sha256")
    if (
        not isinstance(keyset_sha256, str)
        or not keyset_sha256.startswith("sha256:")
        or len(keyset_sha256) != 71
    ):
        _fail(result, "keyset_sha256 is malformed")
        return None

    catalogs = localization.get("catalogs")
    if not isinstance(catalogs, dict) or list(catalogs) != list(SUPPORTED_LOCALES):
        _fail(result, "catalogs must contain en, zh-TW, ja in order")
        return None

    runtime_catalogs: dict[str, dict[str, Any]] = {}
    for locale in SUPPORTED_LOCALES:
        catalog = catalogs.get(locale)
        if not isinstance(catalog, dict):
            _fail(result, f"catalog descriptor for {locale} must be an object")
            return None

        asset_path = str(catalog.get("asset_path") or "")
        if asset_path != f"locales/{locale}.json":
            _fail(result, f"{locale} asset_path must be locales/{locale}.json")
            return None

        try:
            expected_bytes = int(catalog.get("bytes"))
        except (TypeError, ValueError):
            _fail(result, f"{locale} bytes must be an integer")
            return None
        if expected_bytes <= 0 or expected_bytes > MAX_COMPILED_CATALOG_BYTES:
            _fail(result, f"{locale} bytes exceeds the compiled catalog budget")
            return None

        expected_integrity = catalog.get("integrity")
        if (
            not isinstance(expected_integrity, str)
            or not expected_integrity.startswith("sha256-")
        ):
            _fail(result, f"{locale} integrity is malformed")
            return None

        try:
            source_asset = _safe_source_asset(source_ui_dist_dir, asset_path)
        except ValueError as exc:
            _fail(result, str(exc))
            return None
        if not source_asset.is_file():
            _fail(result, f"{locale} compiled catalog is missing")
            return None
        if source_asset.stat().st_size != expected_bytes:
            _fail(result, f"{locale} byte count does not match the descriptor")
            return None
        if _sha256_integrity(source_asset) != expected_integrity:
            _fail(result, f"{locale} integrity does not match the descriptor")
            return None

        target_asset = target_assets_dir / asset_path
        target_asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_asset, target_asset)
        runtime_catalogs[locale] = {
            "asset_path": f"{version_segment}/{asset_path}",
            "asset_url": (
                f"/api/v1/capability-packs/installed-capabilities/"
                f"{capability_code}/ui-assets/{version_segment}/{asset_path}"
            ),
            "integrity": expected_integrity,
            "bytes": expected_bytes,
        }

    return {
        **expected_scalars,
        "supported_locales": list(SUPPORTED_LOCALES),
        "keyset_sha256": keyset_sha256,
        "catalogs": runtime_catalogs,
    }

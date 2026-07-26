import base64
import hashlib
import json
from pathlib import Path

from app.routes.core.capability_packs_core.installed_runtime_localization import (
    project_installed_ui_localization,
)
from app.services.install_result import InstallResult
from app.services.runtime_assets_installer_core.ui_localization_assets import (
    install_ui_localization_assets,
)


def _integrity(value: bytes) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(value).digest()).decode()


def _fixture(source: Path, capability_code: str = "demo_pack") -> dict:
    keyset = f"sha256:{hashlib.sha256(b'greeting').hexdigest()}"
    catalogs = {}
    for locale in ("en", "zh-TW", "ja"):
        value = (
            json.dumps(
                {
                    "format": "formatjs-icu-messageformat-ast-v1",
                    "compiler": "@formatjs/icu-messageformat-parser@3.5.15",
                    "namespace": capability_code,
                    "locale": locale,
                    "keyset_sha256": keyset,
                    "messages": {"greeting": [{"type": 0, "value": locale}]},
                },
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        path = source / "locales" / f"{locale}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        catalogs[locale] = {
            "asset_path": f"locales/{locale}.json",
            "integrity": _integrity(value),
            "bytes": len(value),
        }
    return {
        "contract": "mindscape-capability-ui-localization-v1",
        "namespace": capability_code,
        "source_locale": "en",
        "fallback_locale": "en",
        "format": "formatjs-icu-messageformat-ast-v1",
        "compiler": "@formatjs/icu-messageformat-parser@3.5.15",
        "supported_locales": ["en", "zh-TW", "ja"],
        "keyset_sha256": keyset,
        "catalogs": catalogs,
    }


def test_installs_exact_localization_descriptor_into_component_asset_lane(
    tmp_path: Path,
):
    source = tmp_path / "ui_dist"
    target = tmp_path / "assets" / "demo_pack" / "1.2.3"
    descriptor = _fixture(source)
    result = InstallResult()

    runtime = install_ui_localization_assets(
        source_ui_dist_dir=source,
        target_assets_dir=target,
        capability_code="demo_pack",
        version_segment="1.2.3",
        localization=descriptor,
        result=result,
    )

    assert result.errors == []
    assert runtime is not None
    assert list(runtime["catalogs"]) == ["en", "zh-TW", "ja"]
    assert runtime["catalogs"]["ja"]["asset_url"].endswith(
        "/demo_pack/ui-assets/1.2.3/locales/ja.json"
    )
    assert (target / "locales" / "ja.json").is_file()
    assert project_installed_ui_localization({"localization": runtime}) == runtime


def test_rejects_catalog_integrity_mismatch_without_projecting_empty_descriptor(
    tmp_path: Path,
):
    source = tmp_path / "ui_dist"
    descriptor = _fixture(source)
    descriptor["catalogs"]["zh-TW"]["integrity"] = "sha256-invalid"
    result = InstallResult()

    runtime = install_ui_localization_assets(
        source_ui_dist_dir=source,
        target_assets_dir=tmp_path / "target",
        capability_code="demo_pack",
        version_segment="1.2.3",
        localization=descriptor,
        result=result,
    )

    assert runtime is None
    assert result.errors == [
        "Capability UI localization is invalid: "
        "zh-TW integrity does not match the descriptor"
    ]
    assert project_installed_ui_localization({}) is None

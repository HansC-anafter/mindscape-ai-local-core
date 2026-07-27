from pathlib import Path

import yaml
from jsonschema import Draft7Validator


LOCAL_CORE_ROOT = Path(__file__).resolve().parents[2]
CLOUD_ROOT = LOCAL_CORE_ROOT.parent / "mindscape-ai-cloud"


def _load_schema(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_local_manifest_schema_matches_cloud_localization_contract() -> None:
    local_schema = _load_schema(LOCAL_CORE_ROOT / "schemas" / "manifest.schema.yaml")
    cloud_schema = _load_schema(
        CLOUD_ROOT / "capabilities" / "manifest.schema.yaml"
    )

    local_properties = local_schema["properties"]
    cloud_properties = cloud_schema["properties"]
    assert (
        local_properties["ui_components"]["items"]["properties"]["domain_path"]
        == cloud_properties["ui_components"]["items"]["properties"]["domain_path"]
    )
    assert local_properties["ui_localization"] == cloud_properties["ui_localization"]


def test_local_manifest_schema_accepts_localized_pack_source_contract() -> None:
    schema = _load_schema(LOCAL_CORE_ROOT / "schemas" / "manifest.schema.yaml")
    manifest = {
        "code": "demo_localized_pack",
        "version": "1.2.3",
        "portability": {
            "min_local_core_version": "1.0.0",
            "environments": ["local-core"],
        },
        "ui_components": [
            {
                "code": "DemoWorkbench",
                "path": "ui/localized-entries/DemoWorkbench.tsx",
                "domain_path": "ui/DemoWorkbench.tsx",
                "export": "default",
                "type": "capability_page",
            }
        ],
        "ui_localization": {
            "contract": "mindscape-capability-ui-localization-v1",
            "namespace": "demo_localized_pack",
            "source_locale": "en",
            "fallback_locale": "en",
            "supported_locales": ["en", "zh-TW", "ja"],
            "catalogs": {
                "en": "ui/i18n/en.json",
                "zh-TW": "ui/i18n/zh-TW.json",
                "ja": "ui/i18n/ja.json",
            },
        },
    }

    errors = sorted(
        Draft7Validator(schema).iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )

    assert errors == []


def test_local_manifest_schema_accepts_web_generation_release_manifest() -> None:
    schema = _load_schema(LOCAL_CORE_ROOT / "schemas" / "manifest.schema.yaml")
    manifest = _load_schema(
        CLOUD_ROOT / "capabilities" / "web_generation" / "manifest.yaml"
    )

    errors = sorted(
        Draft7Validator(schema).iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )

    assert errors == []

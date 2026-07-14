import asyncio

import pytest
from fastapi import HTTPException

from backend.app.routes.core import settings_extensions
from backend.app.routes.core.capability_packs_core import installed_routes
from backend.app.routes.core.settings_extensions_core import (
    manifest_catalog,
    projection,
)


def _run(
    *,
    capability_code: str | None,
    component_code: str | None,
    db=object(),
):
    return asyncio.run(
        settings_extensions.get_settings_extensions(
            section="remote-workbench-global-access",
            workspace_id=None,
            capability_code=capability_code,
            component_code=component_code,
            db=db,
        )
    )


class _NoRegistryDb:
    def query(self, *_args, **_kwargs):
        raise AssertionError("runtime registry SQL must remain unused")

    def execute(self, *_args, **_kwargs):
        raise AssertionError("service registry SQL must remain unused")


def test_exact_owner_reads_only_the_requested_manifest_and_zero_registries(
    monkeypatch,
    tmp_path,
):
    target = tmp_path / "demo"
    target.mkdir()
    target.joinpath("manifest.yaml").write_text(
        """
code: demo
ui_components:
  - code: GlobalAccessPanel
    path: ui/components/GlobalAccessPanel.tsx
    settings:
      section: remote-workbench-global-access
      requires_workspace_id: false
      show_when:
        always: true
""".strip(),
        encoding="utf-8",
    )
    target.joinpath("ui_runtime_assets.json").write_text(
        """
{
  "components": [
    {
      "code": "GlobalAccessPanel",
      "asset_url": "/demo/GlobalAccessPanel.mjs",
      "integrity": "sha256-exact",
      "bytes": 41,
      "runtime": "mindscape-react-bridge-v1"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    unrelated.joinpath("manifest.yaml").write_text(
        "code: unrelated\nui_components: []\n",
        encoding="utf-8",
    )
    manifest_reads = []
    original_safe_load = manifest_catalog.yaml.safe_load

    def tracked_safe_load(stream):
        manifest_reads.append(stream.name)
        return original_safe_load(stream)

    monkeypatch.setattr(
        manifest_catalog,
        "get_capabilities_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(manifest_catalog.yaml, "safe_load", tracked_safe_load)

    def reject_pack_scan(_capability_code):
        raise AssertionError("exact owner must not scan pack metadata")

    monkeypatch.setattr(
        installed_routes,
        "get_cached_runtime_ui_index",
        lambda _capability_code: None,
    )
    monkeypatch.setattr(
        installed_routes,
        "set_cached_runtime_ui_index",
        lambda _capability_code, _payload: None,
    )
    monkeypatch.setattr(
        installed_routes,
        "_get_pack_meta_by_code",
        reject_pack_scan,
    )

    payload = _run(
        capability_code="demo",
        component_code="GlobalAccessPanel",
        db=_NoRegistryDb(),
    )

    assert [panel["component_code"] for panel in payload] == [
        "GlobalAccessPanel"
    ]
    assert manifest_reads == [str(target / "manifest.yaml")]


@pytest.mark.parametrize(
    ("capability_code", "component_code"),
    [
        ("demo", None),
        (None, "GlobalAccessPanel"),
    ],
)
def test_exact_owner_query_requires_both_identifiers(
    capability_code,
    component_code,
):
    with pytest.raises(HTTPException) as exc_info:
        _run(
            capability_code=capability_code,
            component_code=component_code,
        )

    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    ("capability_code", "component_code"),
    [
        ("../demo", "GlobalAccessPanel"),
        ("demo/path", "GlobalAccessPanel"),
        ("demo%2fescape", "GlobalAccessPanel"),
        ("demo", "../GlobalAccessPanel"),
        ("demo", "Global.AccessPanel"),
        ("a" * 129, "GlobalAccessPanel"),
    ],
)
def test_exact_owner_query_rejects_unbounded_or_path_identifiers(
    monkeypatch,
    capability_code,
    component_code,
):
    projection_calls = []
    monkeypatch.setattr(
        projection,
        "get_settings_extension_descriptors",
        lambda **_kwargs: projection_calls.append(True) or [],
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            capability_code=capability_code,
            component_code=component_code,
        )

    assert exc_info.value.status_code == 422
    assert projection_calls == []


def test_unknown_exact_owner_does_not_read_unrelated_manifests(
    monkeypatch,
    tmp_path,
):
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    unrelated.joinpath("manifest.yaml").write_text(
        "code: unrelated\nui_components: []\n",
        encoding="utf-8",
    )
    manifest_reads = []
    original_safe_load = manifest_catalog.yaml.safe_load

    def tracked_safe_load(stream):
        manifest_reads.append(stream.name)
        return original_safe_load(stream)

    monkeypatch.setattr(
        manifest_catalog,
        "get_capabilities_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(manifest_catalog.yaml, "safe_load", tracked_safe_load)

    payload = _run(
        capability_code="unknown",
        component_code="GlobalAccessPanel",
        db=_NoRegistryDb(),
    )

    assert payload == []
    assert manifest_reads == []


def test_exact_owner_rejects_manifest_symlink_escape(monkeypatch, tmp_path):
    capabilities_dir = tmp_path / "capabilities"
    capabilities_dir.mkdir()
    outside_pack = tmp_path / "outside-pack"
    outside_pack.mkdir()
    outside_pack.joinpath("manifest.yaml").write_text(
        "code: demo\nui_components: []\n",
        encoding="utf-8",
    )
    capabilities_dir.joinpath("demo").symlink_to(
        outside_pack,
        target_is_directory=True,
    )
    monkeypatch.setattr(
        manifest_catalog,
        "get_capabilities_dir",
        lambda: capabilities_dir,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            capability_code="demo",
            component_code="GlobalAccessPanel",
            db=_NoRegistryDb(),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "settings_extensions_unavailable"


def test_exact_owner_rejects_manifest_capability_code_mismatch(
    monkeypatch,
    tmp_path,
):
    target = tmp_path / "demo"
    target.mkdir()
    target.joinpath("manifest.yaml").write_text(
        "code: other\nui_components: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        manifest_catalog,
        "get_capabilities_dir",
        lambda: tmp_path,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            capability_code="demo",
            component_code="GlobalAccessPanel",
            db=_NoRegistryDb(),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "settings_extensions_unavailable"


def test_exact_owner_malformed_descriptor_does_not_fallback_to_generic(
    monkeypatch,
):
    generic_scans = []
    monkeypatch.setattr(
        manifest_catalog,
        "load_exact_owner_manifest",
        lambda _code: {
            "code": "demo",
            "ui_components": {"not": "a list"},
        },
    )
    monkeypatch.setattr(
        manifest_catalog,
        "get_installed_capabilities",
        lambda: generic_scans.append(True) or ["unrelated"],
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            capability_code="demo",
            component_code="GlobalAccessPanel",
            db=_NoRegistryDb(),
        )

    assert exc_info.value.status_code == 500
    assert generic_scans == []


def test_exact_owner_component_code_mismatch_is_not_projected(monkeypatch):
    runtime_reads = []
    monkeypatch.setattr(
        manifest_catalog,
        "load_exact_owner_manifest",
        lambda _code: {
            "code": "demo",
            "ui_components": [
                {
                    "code": "OtherPanel",
                    "path": "ui/components/OtherPanel.tsx",
                    "settings": {
                        "section": "remote-workbench-global-access",
                        "show_when": {"always": True},
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        projection,
        "_get_runtime_ui_component",
        lambda *_args, **_kwargs: runtime_reads.append(True) or {},
    )

    payload = _run(
        capability_code="demo",
        component_code="GlobalAccessPanel",
        db=_NoRegistryDb(),
    )

    assert payload == []
    assert runtime_reads == []


def test_exact_owner_runtime_sidecar_error_is_strict_and_has_no_fallback(
    monkeypatch,
):
    generic_scans = []
    strict_reads = []
    monkeypatch.setattr(
        manifest_catalog,
        "load_exact_owner_manifest",
        lambda _code: {
            "code": "demo",
            "ui_components": [
                {
                    "code": "GlobalAccessPanel",
                    "path": "ui/components/GlobalAccessPanel.tsx",
                    "settings": {
                        "section": "remote-workbench-global-access",
                        "show_when": {"always": True},
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        manifest_catalog,
        "get_installed_capabilities",
        lambda: generic_scans.append(True) or ["unrelated"],
    )

    def raise_sidecar_error(
        _capability,
        _component,
        *,
        strict=False,
        manifest_file=None,
    ):
        strict_reads.append(strict)
        assert manifest_file is None
        raise RuntimeError("sidecar unavailable")

    monkeypatch.setattr(
        projection,
        "_get_runtime_ui_component",
        raise_sidecar_error,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            capability_code="demo",
            component_code="GlobalAccessPanel",
            db=_NoRegistryDb(),
        )

    assert exc_info.value.status_code == 500
    assert strict_reads == [True]
    assert generic_scans == []


def test_exact_owner_conditional_descriptor_fails_without_registry_sql(
    monkeypatch,
):
    monkeypatch.setattr(
        manifest_catalog,
        "load_exact_owner_manifest",
        lambda _code: {
            "code": "demo",
            "ui_components": [
                {
                    "code": "GlobalAccessPanel",
                    "path": "ui/components/GlobalAccessPanel.tsx",
                    "settings": {
                        "section": "remote-workbench-global-access",
                        "show_when": {"runtime_codes": ["runtime-a"]},
                    },
                }
            ],
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(
            capability_code="demo",
            component_code="GlobalAccessPanel",
            db=_NoRegistryDb(),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "settings_extensions_unavailable"

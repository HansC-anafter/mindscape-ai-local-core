import asyncio

import pytest
from fastapi import HTTPException

from backend.app.routes.core import settings_extensions
from backend.app.routes.core.capability_packs_core import installed_routes


def _component(
    code: str,
    *,
    section: str,
    requires_workspace_id: bool,
    show_when: dict,
) -> dict:
    return {
        "code": code,
        "path": f"ui/components/{code}.tsx",
        "export": "default",
        "settings": {
            "section": section,
            "title": code,
            "requires_workspace_id": requires_workspace_id,
            "show_when": show_when,
        },
    }


def _run(*, section: str, workspace_id: str | None, db=object()):
    return asyncio.run(
        settings_extensions.get_settings_extensions(
            section=section,
            workspace_id=workspace_id,
            db=db,
        )
    )


def test_always_global_extension_avoids_db_reads_and_keeps_runtime_asset_metadata(
    monkeypatch,
):
    component = _component(
        "GlobalAccessPanel",
        section="remote-workbench-global-access",
        requires_workspace_id=False,
        show_when={
            "always": True,
            "runtime_codes": ["unused-runtime"],
            "service_codes": ["unused-service"],
        },
    )
    monkeypatch.setattr(settings_extensions, "get_installed_capabilities", lambda: ["demo"])
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda _code: {"ui_components": [component]},
    )
    runtime_reads = []
    service_reads = []
    monkeypatch.setattr(
        settings_extensions,
        "get_registered_runtime_codes",
        lambda _db: runtime_reads.append(True) or [],
    )
    monkeypatch.setattr(
        settings_extensions,
        "get_registered_service_codes",
        lambda _db: service_reads.append(True) or [],
    )
    monkeypatch.setattr(
        settings_extensions,
        "_get_runtime_ui_component",
        lambda _code, _component, **_kwargs: {
            "asset_url": "/api/v1/capability-packs/installed-capabilities/demo/ui-assets/1/panel.js",
            "integrity": "sha256-demo",
            "bytes": 123,
            "runtime": "mindscape-react-bridge-v1",
            "asset_path": "1/panel.js",
        },
    )

    payload = _run(
        section="remote-workbench-global-access",
        workspace_id=None,
    )

    assert runtime_reads == []
    assert service_reads == []
    assert payload == [
        {
            "capability_code": "demo",
            "component_code": "GlobalAccessPanel",
            "path": "ui/components/GlobalAccessPanel.tsx",
            "import_path": "@/app/capabilities/demo/components/GlobalAccessPanel",
            "export": "default",
            "section": "remote-workbench-global-access",
            "title": "GlobalAccessPanel",
            "description": None,
            "order": 100,
            "requires_workspace_id": False,
            "display_mode": None,
            "show_when": {
                "always": True,
                "runtime_codes": ["unused-runtime"],
                "service_codes": ["unused-service"],
            },
            "props_schema": None,
            "legacy_context": None,
            "asset_url": "/api/v1/capability-packs/installed-capabilities/demo/ui-assets/1/panel.js",
            "integrity": "sha256-demo",
            "bytes": 123,
            "runtime": "mindscape-react-bridge-v1",
            "asset_path": "1/panel.js",
        }
    ]


def test_workspace_projection_excludes_global_extensions(monkeypatch):
    components = [
        _component(
            "GlobalPanel",
            section="runtime-environments",
            requires_workspace_id=False,
            show_when={"always": True},
        ),
        _component(
            "WorkspacePanel",
            section="runtime-environments",
            requires_workspace_id=True,
            show_when={"always": True},
        ),
    ]
    monkeypatch.setattr(settings_extensions, "get_installed_capabilities", lambda: ["demo"])
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda _code: {"ui_components": components},
    )
    monkeypatch.setattr(settings_extensions, "_get_runtime_ui_component", lambda *_args, **_kwargs: {})

    payload = _run(section="runtime-environments", workspace_id="ws-1")

    assert [panel["component_code"] for panel in payload] == ["WorkspacePanel"]


def test_show_when_queries_only_the_required_registries(monkeypatch):
    components = [
        _component(
            "RuntimePanel",
            section="runtime-environments",
            requires_workspace_id=False,
            show_when={"runtime_codes": ["runtime-a"]},
        ),
        _component(
            "ServicePanel",
            section="runtime-environments",
            requires_workspace_id=False,
            show_when={"service_codes": ["service-a"]},
        ),
    ]
    monkeypatch.setattr(settings_extensions, "get_installed_capabilities", lambda: ["demo"])
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda _code: {"ui_components": components},
    )
    monkeypatch.setattr(settings_extensions, "_get_runtime_ui_component", lambda *_args, **_kwargs: {})
    runtime_reads = []
    service_reads = []
    monkeypatch.setattr(
        settings_extensions,
        "get_registered_runtime_codes",
        lambda _db: runtime_reads.append(True) or ["runtime-a"],
    )
    monkeypatch.setattr(
        settings_extensions,
        "get_registered_service_codes",
        lambda _db: service_reads.append(True) or ["service-a"],
    )

    payload = _run(section="runtime-environments", workspace_id=None)

    assert runtime_reads == [True]
    assert service_reads == [True]
    assert [panel["component_code"] for panel in payload] == [
        "RuntimePanel",
        "ServicePanel",
    ]


def test_runtime_condition_does_not_read_the_ignored_service_registry(monkeypatch):
    component = _component(
        "RuntimeFirstPanel",
        section="runtime-environments",
        requires_workspace_id=False,
        show_when={
            "runtime_codes": ["runtime-a"],
            "service_codes": ["unused-service"],
        },
    )
    monkeypatch.setattr(settings_extensions, "get_installed_capabilities", lambda: ["demo"])
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda _code: {"ui_components": [component]},
    )
    monkeypatch.setattr(settings_extensions, "_get_runtime_ui_component", lambda *_args, **_kwargs: {})
    runtime_reads = []
    service_reads = []
    monkeypatch.setattr(
        settings_extensions,
        "get_registered_runtime_codes",
        lambda _db: runtime_reads.append(True) or ["runtime-a"],
    )
    monkeypatch.setattr(
        settings_extensions,
        "get_registered_service_codes",
        lambda _db: service_reads.append(True) or ["unused-service"],
    )

    payload = _run(section="runtime-environments", workspace_id=None)

    assert runtime_reads == [True]
    assert service_reads == []
    assert [panel["component_code"] for panel in payload] == ["RuntimeFirstPanel"]


def test_unexpected_runtime_metadata_error_is_reported_as_5xx(monkeypatch):
    component = _component(
        "BrokenMetadataPanel",
        section="runtime-environments",
        requires_workspace_id=False,
        show_when={"always": True},
    )
    monkeypatch.setattr(settings_extensions, "get_installed_capabilities", lambda: ["demo"])
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda _code: {"ui_components": [component]},
    )
    def raise_metadata_error(*_args, **_kwargs):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(
        settings_extensions,
        "_get_runtime_ui_component",
        raise_metadata_error,
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(section="runtime-environments", workspace_id=None)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "settings_extensions_unavailable"


def test_corrupt_runtime_sidecar_is_reported_as_5xx(monkeypatch, tmp_path):
    component = _component(
        "CorruptSidecarPanel",
        section="runtime-environments",
        requires_workspace_id=False,
        show_when={"always": True},
    )
    pack_dir = tmp_path / "corrupt-sidecar"
    pack_dir.mkdir()
    manifest_path = pack_dir / "manifest.yaml"
    manifest_path.write_text("code: corrupt-sidecar\n", encoding="utf-8")
    (pack_dir / "ui_runtime_assets.json").write_text("{broken", encoding="utf-8")

    monkeypatch.setattr(
        settings_extensions,
        "get_installed_capabilities",
        lambda: ["corrupt-sidecar"],
    )
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda _code: {"ui_components": [component]},
    )
    monkeypatch.setattr(
        installed_routes,
        "_get_pack_meta_by_code",
        lambda _code: {"_file_path": str(manifest_path)},
    )

    with pytest.raises(HTTPException) as exc_info:
        _run(section="runtime-environments", workspace_id=None)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "settings_extensions_unavailable"


def test_one_unreadable_manifest_isolated_as_no_descriptor(monkeypatch):
    monkeypatch.setattr(settings_extensions, "get_installed_capabilities", lambda: ["broken"])
    monkeypatch.setattr(settings_extensions, "load_manifest", lambda _code: None)

    assert _run(section="runtime-environments", workspace_id=None) == []


def test_one_malformed_manifest_does_not_hide_a_valid_pack(monkeypatch):
    valid_component = _component(
        "ValidPanel",
        section="runtime-environments",
        requires_workspace_id=False,
        show_when={"always": True},
    )
    manifests = {
        "broken": {"ui_components": {"not": "a list"}},
        "valid": {"ui_components": [valid_component]},
    }
    monkeypatch.setattr(
        settings_extensions,
        "get_installed_capabilities",
        lambda: ["broken", "valid"],
    )
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda code: manifests[code],
    )
    monkeypatch.setattr(settings_extensions, "_get_runtime_ui_component", lambda *_args, **_kwargs: {})

    payload = _run(section="runtime-environments", workspace_id=None)

    assert [panel["component_code"] for panel in payload] == ["ValidPanel"]


def test_one_malformed_component_does_not_hide_a_valid_pack(monkeypatch):
    valid_component = _component(
        "ValidPanel",
        section="runtime-environments",
        requires_workspace_id=False,
        show_when={"always": True},
    )
    manifests = {
        "broken": {"ui_components": ["not-an-object"]},
        "valid": {"ui_components": [valid_component]},
    }
    monkeypatch.setattr(
        settings_extensions,
        "get_installed_capabilities",
        lambda: ["broken", "valid"],
    )
    monkeypatch.setattr(
        settings_extensions,
        "load_manifest",
        lambda code: manifests[code],
    )
    monkeypatch.setattr(
        settings_extensions,
        "_get_runtime_ui_component",
        lambda *_args, **_kwargs: {},
    )

    payload = _run(section="runtime-environments", workspace_id=None)

    assert [panel["component_code"] for panel in payload] == ["ValidPanel"]

import json
from pathlib import Path

import yaml

from backend.tests.capability_packs_cache_support import (
    _reset_pack_yaml_cache,
    capability_packs,
)
from backend.app.routes.core.capability_packs_core import installed_routes
from backend.app.routes.core.capability_packs_core.mobile_workbench_gateway_support import (
    build_mobile_workbench_gateway_support_payload,
)


def test_yogacoach_manifest_supports_workspace_scoped_remote_workbench():
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "capabilities"
        / "yogacoach"
        / "manifest.yaml"
    )
    pack_meta = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    payload = build_mobile_workbench_gateway_support_payload(
        "yogacoach",
        pack_meta,
    )

    assert payload["supported"] is True
    assert payload["host_route_template"] == (
        "/workspaces/{workspaceId}/capability-ui-hosts/yogacoach"
    )
    assert payload["request_scope_contract"] == "explicit_workspace_v1"
    assert payload["api_prefixes"] == ["/api/v1/capabilities/yogacoach"]


def test_mobile_workbench_gateway_support_rejects_unowned_api_prefix(monkeypatch):
    _reset_pack_yaml_cache()
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "browser_capture",
            "code": "browser_capture",
            "remote_workbench": {
                "request_scope_contract": "explicit_workspace_v1"
            },
            "ui_components": [{"code": "BrowserCaptureWorkbench"}],
            "apis": [{"prefix": "/api/v1"}],
        },
    )
    monkeypatch.setattr(
        capability_packs,
        "_get_installed_pack_ids",
        lambda: {"browser_capture"},
    )

    payload = capability_packs.get_capability_mobile_workbench_gateway_support(
        "browser_capture"
    )

    assert payload["supported"] is False
    assert payload["host_route_template"] is None
    assert payload["api_prefixes"] == []


def test_mobile_workbench_gateway_support_requires_request_scope_contract(monkeypatch):
    _reset_pack_yaml_cache()
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "ig_content_generator",
            "code": "ig_content_generator",
            "ui_components": [{"code": "IGWorkbenchPage"}],
            "apis": [
                {"prefix": "/api/v1/capabilities/ig_content_generator"}
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs,
        "_get_installed_pack_ids",
        lambda: {"ig_content_generator"},
    )

    payload = capability_packs.get_capability_mobile_workbench_gateway_support(
        "ig_content_generator"
    )

    assert payload["supported"] is False
    assert payload["host_route_template"] is None
    assert payload["request_scope_contract"] is None


def test_installed_list_embeds_support_without_extra_request(monkeypatch):
    pack_meta = {
        "id": "dance_motion_coach",
        "code": "dance_motion_coach",
        "name": "Dance Motion Coach",
        "remote_workbench": {"request_scope_contract": "no_remote_requests_v1"},
        "ui_components": [{"code": "DancePracticeWorkbenchPage"}],
        "apis": [],
    }
    monkeypatch.setattr(installed_routes, "_scan_pack_yaml_files", lambda: [pack_meta])
    monkeypatch.setattr(
        installed_routes,
        "_get_installed_pack_ids",
        lambda: {"dance_motion_coach"},
    )

    response = installed_routes.list_installed_capabilities()
    payload = json.loads(response.body)

    assert len(payload) == 1
    assert payload[0]["mobile_workbench_gateway_support"]["supported"] is True
    assert (
        payload[0]["mobile_workbench_gateway_support"]["request_scope_contract"]
        == "no_remote_requests_v1"
    )


def test_no_remote_request_pack_never_projects_declared_api_prefixes(monkeypatch):
    _reset_pack_yaml_cache()
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "live_interface_interpreter",
            "code": "live_interface_interpreter",
            "remote_workbench": {
                "request_scope_contract": "no_remote_requests_v1"
            },
            "ui_components": [
                {"code": "LiveInterfaceInterpreterWorkbench"}
            ],
            "apis": [
                {
                    "prefix": (
                        "/api/v1/capabilities/live_interface_interpreter"
                    )
                }
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs,
        "_get_installed_pack_ids",
        lambda: {"live_interface_interpreter"},
    )

    payload = capability_packs.get_capability_mobile_workbench_gateway_support(
        "live_interface_interpreter"
    )

    assert payload["supported"] is True
    assert payload["request_scope_contract"] == "no_remote_requests_v1"
    assert payload["api_prefixes"] == []

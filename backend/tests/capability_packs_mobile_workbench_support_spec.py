import json

from backend.tests.capability_packs_cache_support import (
    _reset_pack_yaml_cache,
    capability_packs,
)
from backend.app.routes.core.capability_packs_core import installed_routes


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

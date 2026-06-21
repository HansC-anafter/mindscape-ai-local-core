from __future__ import annotations

import json
from types import SimpleNamespace

from backend.app.models.runtime_execution_intent import (
    BindingMode,
    ExecutionBackend,
    PolicyMode,
)
from backend.app.services.execution_intent_resolver import (
    ExecutionIntentResolution,
    ExecutionIntentResolver,
)
from backend.app.services.execution_intent_resolver_core import control_plane


def _task():
    return SimpleNamespace(id=101, workspace_id="workspace-1", pack_id="pack-a")


def _video_intent(**overrides):
    payload = {
        "workload_kind": "video.render",
        "binding_mode": BindingMode.FROZEN_WORKLOAD_SNAPSHOT.value,
        "execution_backend": ExecutionBackend.REMOTE.value,
        "logical_target": "video_renderer_generative",
        "policy_mode": PolicyMode.CLOUD_REQUIRED.value,
        "site_key": "site-a",
    }
    payload.update(overrides)
    return payload


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_prebuilt_remote_routes_short_circuit_resolution(monkeypatch):
    def fail_probe(*args, **kwargs):
        raise AssertionError("prebuilt routes must not probe the control plane")

    monkeypatch.setattr(control_plane, "urlopen", fail_probe)
    resolver = ExecutionIntentResolver()

    result = resolver.resolve(
        task=_task(),
        execution_context={},
        raw_inputs={
            "_remote_tool_routes": {
                "step-a": {
                    "execution_backend": "remote",
                    "tool_name": "capability.tool",
                }
            },
            "workload_execution_intent": {"invalid": object()},
        },
    )

    assert result.effective_route_metadata == {
        "step-a": {
            "execution_backend": "remote",
            "tool_name": "capability.tool",
        }
    }
    assert result.park_task is False


def test_cloud_video_intent_uses_fake_availability_selected_device(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, dict(request.headers), timeout))
        return _FakeResponse({"available": True, "selected_device_id": "device-9"})

    monkeypatch.setenv("EXECUTION_CONTROL_API_URL", "https://control.example")
    monkeypatch.setenv("CLOUD_API_KEY", "token-a")
    monkeypatch.setenv("DEVICE_ID", "runner-1")
    monkeypatch.setattr(control_plane, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        control_plane,
        "inspect_cloud_connector_connected_state",
        lambda: None,
    )

    result = ExecutionIntentResolver().resolve(
        task=_task(),
        execution_context={},
        raw_inputs={
            "workload_execution_intent": _video_intent(),
            "workload_snapshot": {"scene": "a"},
        },
    )

    route = result.effective_route_metadata["video_renderer.vr_render_generative"]
    assert result.resolved_scope == "cloud"
    assert result.resolved_device_id == "device-9"
    assert route["target_device_id"] == "device-9"
    assert route["execution_backend"] == "remote"
    assert calls[0][2] == 2.0
    assert (
        calls[0][0]
        == "https://control.example/api/v1/executions/availability?site_key=site-a"
    )
    assert calls[0][1]["Authorization"] == "Bearer token-a"
    assert calls[0][1]["X-device-id"] == "runner-1"


def test_cloud_required_unavailable_parks_task_with_payload(monkeypatch):
    def fake_urlopen(request, timeout):
        return _FakeResponse(
            {
                "available": False,
                "reason_code": "capacity_full",
                "site_key": "site-a",
                "requested_device_id": "device-requested",
                "selected_device_id": "device-selected",
            }
        )

    monkeypatch.setenv("EXECUTION_CONTROL_API_URL", "https://control.example")
    monkeypatch.setattr(control_plane, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        control_plane,
        "inspect_cloud_connector_connected_state",
        lambda: None,
    )

    result = ExecutionIntentResolver().resolve(
        task=_task(),
        execution_context={},
        raw_inputs={
            "workload_execution_intent": _video_intent(
                target_device_id="device-requested"
            )
        },
    )

    assert result.park_task is True
    assert result.blocked_reason == "runtime_unavailable"
    assert result.blocked_payload == {
        "reason_code": "capacity_full",
        "required_scope": "cloud",
        "policy_mode": "cloud_required",
        "logical_target": "video_renderer_generative",
        "site_key": "site-a",
        "target_device_id": "device-requested",
        "availability_source": "site_hub_control_plane",
        "requested_device_id": "device-requested",
        "selected_device_id": "device-selected",
    }


def test_missing_site_key_does_not_probe_control_plane(monkeypatch):
    def fail_probe(*args, **kwargs):
        raise AssertionError("missing site key must avoid control-plane network probe")

    monkeypatch.delenv("SITE_KEY", raising=False)
    monkeypatch.setenv("EXECUTION_CONTROL_API_URL", "https://control.example")
    monkeypatch.setattr(control_plane, "urlopen", fail_probe)
    monkeypatch.setattr(
        control_plane,
        "inspect_cloud_connector_connected_state",
        lambda: None,
    )

    result = ExecutionIntentResolver().resolve(
        task=_task(),
        execution_context={},
        raw_inputs={
            "workload_execution_intent": _video_intent(site_key=None),
        },
    )

    assert result.resolved_scope == "cloud"
    assert result.park_task is False
    assert result.effective_route_metadata["video_renderer.vr_render_generative"][
        "execution_backend"
    ] == "remote"


def test_public_facade_preserves_resolution_exports():
    resolver = ExecutionIntentResolver()
    assert isinstance(
        ExecutionIntentResolution(effective_inputs={}),
        ExecutionIntentResolution,
    )
    assert resolver._has_prebuilt_remote_routes({"remote_tool_routes": {"a": {}}})
    assert resolver._extract_route_metadata({"remote_tool_routes": {"a": {}}}) == {
        "a": {}
    }

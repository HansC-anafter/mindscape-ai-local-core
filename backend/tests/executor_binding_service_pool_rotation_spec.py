from types import SimpleNamespace

from backend.app.services.executor_binding_service import ExecutorBindingService
from backend.app.services.executor_route_resolver import ExecutorRouteSelection


def _selection(selection_reason="workspace_pool", preferred_runtime_id=None):
    return ExecutorRouteSelection(
        surface="codex_cli",
        executor_runtime="codex_cli",
        requested_workspace_id="workspace-a",
        effective_workspace_id="workspace-a",
        preferred_runtime_id=preferred_runtime_id,
        selection_reason=selection_reason,
        auth_workspace_id="workspace-a",
        source_workspace_id="workspace-a",
    )


def _service_with_binding(binding):
    workspace = SimpleNamespace(
        id="workspace-a",
        metadata={"executor_route_bindings": {"codex_cli": binding}},
        resolved_executor_runtime="codex_cli",
    )
    return ExecutorBindingService(
        workspace_loader=lambda _workspace_id: workspace,
        workspace_saver=lambda item: item,
    )


def test_pool_rotation_does_not_pin_previous_concrete_runtime():
    service = _service_with_binding(
        {
            "executor_runtime": "codex_cli",
            "preferred_runtime_id": None,
            "concrete_runtime_id": "runtime-codex_cli-previous",
            "binding_state": "resolved",
            "policy_mode": "pool_rotation",
            "selection_reason": "workspace_pool",
            "binding_revision": 3,
            "configured_at": "2026-05-05T00:00:00+00:00",
            "updated_at": "2026-05-05T00:01:00+00:00",
        }
    )

    preference = service.resolve_pool_preference(selection=_selection())

    assert preference["preferred_runtime_id"] is None
    assert preference["allow_runtime_substitution"] is True
    assert preference["preference_source"] == "pool_rotation"
    assert preference["binding_runtime_id"] == "runtime-codex_cli-previous"


def test_non_pool_binding_still_pins_previous_concrete_runtime():
    service = _service_with_binding(
        {
            "executor_runtime": "codex_cli",
            "preferred_runtime_id": None,
            "concrete_runtime_id": "runtime-codex_cli-previous",
            "binding_state": "resolved",
            "policy_mode": "unbound_runtime",
            "selection_reason": "workspace_default",
            "binding_revision": 3,
            "configured_at": "2026-05-05T00:00:00+00:00",
            "updated_at": "2026-05-05T00:01:00+00:00",
        }
    )

    preference = service.resolve_pool_preference(
        selection=_selection(selection_reason="workspace_default")
    )

    assert preference["preferred_runtime_id"] == "runtime-codex_cli-previous"
    assert preference["allow_runtime_substitution"] is False
    assert preference["preference_source"] == "binding_snapshot"

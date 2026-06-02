from backend.app.routes.core.capability_install_core.restart_policy import (
    INSTALL_RESTART_SEMANTICS_VERSION,
    apply_restart_decision_to_payload,
    build_install_restart_decision,
    refresh_restart_decision_after_execution,
)


def test_activated_pack_install_does_not_require_backend_or_runner_restart():
    decision = build_install_restart_decision(
        execution_activation_state="activated",
        activation_state="active",
        manifest_hash_matches=True,
    )

    assert decision.backend_process_restart_required is False
    assert decision.runner_restart_required is False
    assert decision.restart_webhook_required is False
    assert decision.legacy_restart_required is False
    assert decision.semantic_version == INSTALL_RESTART_SEMANTICS_VERSION


def test_contract_lane_change_requires_backend_process_restart_only():
    decision = build_install_restart_decision(contract_lane_changed=True)

    assert decision.backend_process_restart_required is True
    assert decision.runner_restart_required is False
    assert decision.restart_webhook_required is True
    assert decision.legacy_restart_required is True
    assert "contract_lane_changed" in decision.reasons


def test_pending_execution_activation_does_not_require_restart():
    decision = build_install_restart_decision(
        execution_activation_state="pending_execution_activation"
    )

    assert decision.backend_process_restart_required is False
    assert decision.runner_restart_required is False
    assert decision.legacy_restart_required is False
    assert "execution_activation_pending" in decision.reasons


def test_apply_restart_decision_flattens_compatibility_payload_fields():
    payload = apply_restart_decision_to_payload(
        {"success": True},
        build_install_restart_decision(contract_lane_changed=True),
    )

    assert payload["restart_required"] is True
    assert payload["backend_process_restart_required"] is True
    assert payload["runner_restart_required"] is False
    assert payload["execution_activation_required"] is True
    assert payload["restart_semantics_version"] == INSTALL_RESTART_SEMANTICS_VERSION


def test_refresh_after_execution_activation_clears_legacy_restart_required():
    payload = {
        "restart_required": True,
        "activation": {"manifest_hash": "hash-1"},
        "restart_decision": build_install_restart_decision().to_payload(),
    }
    refreshed = refresh_restart_decision_after_execution(
        payload=payload,
        execution_activation={"state": "activated"},
        activation={
            "pack_id": "ig",
            "install_state": "installed",
            "activation_state": "active",
            "manifest_hash": "hash-1",
        },
    )

    assert refreshed["restart_required"] is False
    assert refreshed["backend_process_restart_required"] is False
    assert refreshed["runner_restart_required"] is False
    assert refreshed["execution_activation_state"] == "activated"
    assert refreshed["restart_semantics_version"] == INSTALL_RESTART_SEMANTICS_VERSION

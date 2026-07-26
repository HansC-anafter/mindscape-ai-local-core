from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.app.services.host_runtime_bindings.contracts import (
    AttestBindingCommand,
    DeclareBindingCommand,
    FinalizeBindingRetirementCommand,
    GrantWorkspaceCommand,
    HostRuntimeCondition,
    RequestBindingRetirementCommand,
)


NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
DIGEST = "a" * 64


def _condition(**overrides):
    payload = {
        "type": "SupervisorReady",
        "status": "true",
        "reason": "process_matches",
        "observed_generation": 1,
        "observed_at": NOW,
    }
    payload.update(overrides)
    return HostRuntimeCondition.model_validate(payload)


def _conditions(**overrides):
    return [
        _condition(type=condition_type, **overrides)
        for condition_type in (
            "Materialized",
            "RuntimeDigestVerified",
            "SupervisorReady",
            "PermissionsReady",
            "ResourceLaneReady",
        )
    ]


def test_binding_command_rejects_extra_keys_bool_generation_and_duplicates():
    payload = {
        "device_id": "device-a",
        "capability_code": "live_interface_interpreter",
        "requirement_code": "live_interface_automation",
        "capability_version": "0.1.36",
        "runtime_digest": DIGEST,
        "host_assets_digest": DIGEST,
        "entrypoint": "scripts/host_runtime_entry.py",
        "entrypoint_digest": "c" * 64,
        "share_policy": "workspace_grants",
        "operations": ["watch-screenshots"],
        "permission_classes": ["filesystem.read"],
        "resource_lane": "host.io.light",
        "expected_generation": 0,
    }
    assert DeclareBindingCommand.model_validate(payload).device_id == "device-a"
    with pytest.raises(ValidationError):
        DeclareBindingCommand.model_validate({**payload, "workspace_id": "ws"})
    with pytest.raises(ValidationError):
        DeclareBindingCommand.model_validate(
            {**payload, "expected_generation": True}
        )
    with pytest.raises(ValidationError, match="must_be_unique"):
        DeclareBindingCommand.model_validate(
            {
                **payload,
                "operations": [
                    "watch-screenshots",
                    "watch-screenshots",
                ],
            }
        )
    with pytest.raises(ValidationError, match="runtime_digest_must_match"):
        DeclareBindingCommand.model_validate(
            {**payload, "host_assets_digest": "b" * 64}
        )


def test_attestation_requires_exact_generation_and_unique_conditions():
    payload = {
        "binding_id": "binding-a",
        "generation": 1,
        "runtime_digest": DIGEST,
        "executor_identity_digest": "b" * 64,
        "permission_revision": 1,
        "conditions": _conditions(),
        "observed_at": NOW,
    }
    assert AttestBindingCommand.model_validate(payload).generation == 1
    with pytest.raises(ValidationError, match="generation_mismatch"):
        AttestBindingCommand.model_validate(
            {
                **payload,
                "conditions": _conditions(observed_generation=2),
            }
        )
    with pytest.raises(ValidationError, match="must_be_unique"):
        AttestBindingCommand.model_validate(
            {**payload, "conditions": [_condition(), _condition()]}
        )
    with pytest.raises(ValidationError, match="types_incomplete"):
        AttestBindingCommand.model_validate(
            {**payload, "conditions": [_condition()]}
        )


def test_voice_scoped_grant_is_atomic_and_timezone_aware():
    payload = {
        "workspace_id": "workspace-a",
        "binding_id": "binding-a",
        "binding_generation": 1,
        "operation": "watch-screenshots",
        "operation_args_sha256": "d" * 64,
        "policy_revision": 2,
        "attestation_revision": 3,
        "expires_at": NOW + timedelta(hours=1),
        "provider_code": "f5_tts_mlx",
        "voice_profile_id": "cheng-yi-jia",
        "reference_rights_revision": 4,
    }
    assert GrantWorkspaceCommand.model_validate(payload).provider_code == "f5_tts_mlx"
    with pytest.raises(ValidationError, match="voice_scope_must_be_complete"):
        GrantWorkspaceCommand.model_validate(
            {**payload, "reference_rights_revision": None}
        )
    with pytest.raises(ValidationError, match="timezone_aware"):
        GrantWorkspaceCommand.model_validate(
            {**payload, "expires_at": datetime(2026, 7, 27)}
        )


def test_retirement_commands_are_generation_bound_and_cleanup_is_exact_true():
    request = RequestBindingRetirementCommand.model_validate(
        {
            "binding_id": "binding-a",
            "generation": 2,
            "reason": "capability_upgrade",
        }
    )
    assert request.generation == 2
    with pytest.raises(ValidationError):
        RequestBindingRetirementCommand.model_validate(
            {
                "binding_id": "binding-a",
                "generation": True,
                "reason": "capability_upgrade",
            }
        )
    with pytest.raises(ValidationError):
        FinalizeBindingRetirementCommand.model_validate(
            {
                "binding_id": "binding-a",
                "generation": 2,
                "supervisor_cleanup_terminal": False,
            }
        )
    assert FinalizeBindingRetirementCommand.model_validate(
        {
            "binding_id": "binding-a",
            "generation": 2,
            "supervisor_cleanup_terminal": True,
        }
    ).supervisor_cleanup_terminal is True

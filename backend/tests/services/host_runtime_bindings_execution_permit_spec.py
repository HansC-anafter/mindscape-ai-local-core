from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from backend.app.services.host_runtime_bindings.execution_permit import (
    verify_execution_permit,
)
from backend.app.services.host_runtime_bindings.facade import (
    HostRuntimeBindingFacade,
)


NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
SECRET = "s" * 32


class FakeRepository:
    def __init__(self, operation_args: list[str] | None = None):
        self.operation_args = operation_args or []

    def load_effective_records(self, **_kwargs):
        conditions = [
            {
                "type": condition_type,
                "status": "true",
                "reason": "verified",
                "observed_generation": 2,
                "observed_at": NOW.isoformat(),
            }
            for condition_type in (
                "Materialized",
                "RuntimeDigestVerified",
                "SupervisorReady",
                "PermissionsReady",
                "ResourceLaneReady",
            )
        ]
        return {
            "binding": {
                "id": "binding-a",
                "device_id": "device-a",
                "capability_code": "live_interface_interpreter",
                "requirement_code": "live_interface_automation",
                "capability_version": "0.1.36",
                "runtime_digest": "a" * 64,
                "host_assets_digest": "a" * 64,
                "entrypoint": "scripts/host_runtime_entry.py",
                "entrypoint_digest": "c" * 64,
                "desired_state": "active",
                "generation": 2,
                "share_policy": "workspace_grants",
                "operations": ["watch-screenshots"],
                "permission_classes": ["filesystem.read"],
                "resource_lane": "host.io.light",
                "materialized_root": "/runtime/lii",
                "finalizers": ["mindscape.ai/host-runtime-cleanup"],
            },
            "attestation": {
                "revision": 4,
                "observed_generation": 2,
                "runtime_digest": "a" * 64,
                "executor_identity_digest": "d" * 64,
                "permission_revision": 3,
                "conditions": conditions,
                "observed_at": NOW.isoformat(),
            },
            "grant": {
                "id": "grant-a",
                "workspace_id": "workspace-a",
                "binding_id": "binding-a",
                "binding_generation": 2,
                "operation": "watch-screenshots",
                "operation_args_sha256": sha256(
                    json.dumps(
                        self.operation_args,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                "policy_revision": 3,
                "attestation_revision": 4,
                "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
                "status": "active",
                "provider_code": "f5_tts_mlx",
                "voice_profile_id": "cheng-yi-jia",
                "reference_rights_revision": 7,
            },
        }


def test_execution_permit_binds_exact_composite_and_expires_within_sixty_seconds():
    permit = HostRuntimeBindingFacade(
        repository=FakeRepository(["--workspace-id", "workspace-a"])
    ).issue_execution_permit(
        workspace_id="workspace-a",
        capability_code="live_interface_interpreter",
        requirement_code="live_interface_automation",
        operation="watch-screenshots",
        operation_args=["--workspace-id", "workspace-a"],
        now=NOW,
        secret=SECRET,
    )

    verify_execution_permit(permit, secret=SECRET)
    assert permit.claims.binding_generation == 2
    assert permit.claims.operation_args_sha256 == sha256(
        json.dumps(
            ["--workspace-id", "workspace-a"],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert permit.claims.attestation_revision == 4
    assert permit.claims.policy_revision == 3
    assert permit.claims.entrypoint == "scripts/host_runtime_entry.py"
    assert permit.claims.provider_code == "f5_tts_mlx"
    assert permit.claims.voice_profile_id == "cheng-yi-jia"
    assert permit.claims.expires_at == NOW + timedelta(seconds=60)


def test_execution_permit_tamper_and_missing_secret_fail_closed():
    permit = HostRuntimeBindingFacade(
        repository=FakeRepository()
    ).issue_execution_permit(
        workspace_id="workspace-a",
        capability_code="live_interface_interpreter",
        requirement_code="live_interface_automation",
        operation="watch-screenshots",
        operation_args=[],
        now=NOW,
        secret=SECRET,
    )
    tampered = permit.model_copy(deep=True)
    tampered.claims.binding_generation = 3

    with pytest.raises(ValueError, match="signature_invalid"):
        verify_execution_permit(tampered, secret=SECRET)
    with pytest.raises(ValueError, match="secret_unavailable"):
        verify_execution_permit(permit, secret="short")

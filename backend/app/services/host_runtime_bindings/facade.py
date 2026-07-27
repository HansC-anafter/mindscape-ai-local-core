"""Single application entry for host binding and workspace grant authority."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os

from .contracts import (
    AttestBindingCommand,
    DeclareBindingCommand,
    DeviceHostBindingProjection,
    EffectiveHostAdmissionProjection,
    FinalizeBindingRetirementCommand,
    GrantWorkspaceCommand,
    HostOperation,
    HostRuntimeExecutionPermit,
    HostRuntimeExecutionPermitClaims,
    MaterializationReceiptCommand,
    RequestBindingRetirementCommand,
    WorkspaceHostGrantProjection,
)
from .effective_admission import evaluate_effective_host_admission
from .execution_permit import sign_execution_permit
from .grant_policy import validate_grant_command
from .projection import binding_from_record, grant_from_record
from .repository import HostRuntimeBindingRepository


class HostRuntimeBindingFacade:
    """Only application owner for declare/materialize/attest/grant/revoke/read."""

    def __init__(
        self,
        repository: HostRuntimeBindingRepository | None = None,
    ) -> None:
        self.repository = repository or HostRuntimeBindingRepository()

    def declare_binding(
        self,
        command: DeclareBindingCommand,
        *,
        actor_id: str,
    ) -> str:
        return self.repository.declare_binding(command, actor_id=actor_id)

    def record_materialization(
        self,
        command: MaterializationReceiptCommand,
        *,
        actor_id: str,
    ) -> None:
        self.repository.record_materialization(command, actor_id=actor_id)

    def record_attestation(
        self,
        command: AttestBindingCommand,
        *,
        actor_id: str,
    ) -> int:
        return self.repository.record_attestation(command, actor_id=actor_id)

    def grant_workspace(
        self,
        command: GrantWorkspaceCommand,
        *,
        actor_id: str,
        now: datetime | None = None,
    ) -> str:
        binding_record = self.repository.load_binding_record(
            command.binding_id
        )
        if binding_record is None:
            raise ValueError("host_grant_binding_missing")
        binding = binding_from_record(binding_record)
        validate_grant_command(
            binding=binding,
            attestation=binding.attestation,
            command=command,
            now=now,
        )
        return self.repository.create_grant(command, actor_id=actor_id)

    def revoke_workspace_grant(self, grant_id: str, *, actor_id: str) -> None:
        self.repository.revoke_grant(grant_id, actor_id=actor_id)

    def request_binding_retirement(
        self,
        command: RequestBindingRetirementCommand,
        *,
        actor_id: str,
    ) -> None:
        self.repository.request_retirement(command, actor_id=actor_id)

    def finalize_binding_retirement(
        self,
        command: FinalizeBindingRetirementCommand,
        *,
        actor_id: str,
    ) -> None:
        self.repository.finalize_retirement(command, actor_id=actor_id)

    def get_binding(self, binding_id: str) -> DeviceHostBindingProjection:
        record = self.repository.load_binding_record(binding_id)
        if record is None:
            raise ValueError("host_binding_missing")
        return binding_from_record(record)

    def resolve_effective_admission(
        self,
        *,
        workspace_id: str,
        capability_code: str,
        requirement_code: str,
        operation: HostOperation,
        now: datetime | None = None,
    ) -> EffectiveHostAdmissionProjection:
        binding, grant = self._load_projection(
            workspace_id=workspace_id,
            capability_code=capability_code,
            requirement_code=requirement_code,
            operation=operation,
            now=now,
        )
        return evaluate_effective_host_admission(
            workspace_id=workspace_id,
            operation=operation,
            binding=binding,
            grant=grant,
            now=now,
        )

    def issue_execution_permit(
        self,
        *,
        workspace_id: str,
        capability_code: str,
        requirement_code: str,
        operation: HostOperation,
        operation_args: list[str],
        now: datetime | None = None,
        ttl_seconds: int = 60,
        secret: str | None = None,
    ) -> HostRuntimeExecutionPermit:
        observed_now = now or datetime.now(timezone.utc)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 60:
            raise ValueError("host_execution_permit_ttl_invalid")
        if (
            not isinstance(operation_args, list)
            or len(operation_args) > 64
            or any(
                not isinstance(value, str)
                or "\x00" in value
                or len(value) > 1024
                for value in operation_args
            )
        ):
            raise ValueError("host_execution_operation_args_invalid")
        binding, grant = self._load_projection(
            workspace_id=workspace_id,
            capability_code=capability_code,
            requirement_code=requirement_code,
            operation=operation,
            now=observed_now,
        )
        admission = evaluate_effective_host_admission(
            workspace_id=workspace_id,
            operation=operation,
            binding=binding,
            grant=grant,
            now=observed_now,
        )
        if not admission.admitted or binding is None or grant is None:
            blocker = admission.blockers[0] if admission.blockers else "unknown"
            raise ValueError(f"host_execution_admission_blocked:{blocker}")
        if binding.materialized_root is None or binding.attestation is None:
            raise ValueError("host_execution_projection_incomplete")
        operation_args_sha256 = sha256(
            json.dumps(
                operation_args,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if grant.operation_args_sha256 != operation_args_sha256:
            raise ValueError("host_execution_operation_args_not_granted")
        expires_at = min(
            grant.expires_at,
            observed_now + timedelta(seconds=ttl_seconds),
        )
        claims = HostRuntimeExecutionPermitClaims(
            schema_version="mindscape.host-runtime-execution-permit.v1",
            workspace_id=workspace_id,
            binding_id=binding.binding_id,
            binding_generation=binding.generation,
            capability_code=binding.capability_code,
            requirement_code=binding.requirement_code,
            capability_version=binding.capability_version,
            operation=operation,
            operation_args_sha256=operation_args_sha256,
            grant_id=grant.grant_id,
            attestation_revision=binding.attestation.revision,
            policy_revision=grant.policy_revision,
            runtime_digest=binding.runtime_digest,
            host_assets_digest=binding.host_assets_digest,
            entrypoint=binding.entrypoint,
            entrypoint_digest=binding.entrypoint_digest,
            materialized_root=binding.materialized_root,
            permission_classes=binding.permission_classes,
            resource_lane=binding.resource_lane,
            provider_code=grant.provider_code,
            voice_profile_id=grant.voice_profile_id,
            reference_rights_revision=grant.reference_rights_revision,
            issued_at=observed_now,
            expires_at=expires_at,
        )
        signing_secret = secret or os.getenv(
            "HOST_RUNTIME_ADMISSION_HMAC_SECRET",
            "",
        )
        return sign_execution_permit(claims, secret=signing_secret)

    def _load_projection(
        self,
        *,
        workspace_id: str,
        capability_code: str,
        requirement_code: str,
        operation: HostOperation,
        now: datetime | None = None,
    ) -> tuple[
        DeviceHostBindingProjection | None,
        WorkspaceHostGrantProjection | None,
    ]:
        records = self.repository.load_effective_records(
            workspace_id=workspace_id,
            capability_code=capability_code,
            requirement_code=requirement_code,
            operation=operation,
        )
        binding_record = records.get("binding")
        if isinstance(binding_record, dict) and isinstance(
            records.get("attestation"),
            dict,
        ):
            binding_record = {
                **binding_record,
                "attestation": records["attestation"],
            }
        binding = (
            binding_from_record(binding_record)
            if isinstance(binding_record, dict)
            else None
        )
        grant_record = records.get("grant")
        grant = (
            grant_from_record(grant_record, now=now)
            if isinstance(grant_record, dict)
            else None
        )
        return binding, grant

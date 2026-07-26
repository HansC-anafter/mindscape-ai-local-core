"""Transaction-locked workspace grant persistence for host bindings."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from .contracts import GrantWorkspaceCommand
from .grant_policy import validate_grant_command
from .projection import binding_from_record


class HostRuntimeGrantRepositoryMixin:
    """Keep grant causal locks separate from the binding persistence owner."""

    def create_grant(
        self,
        command: GrantWorkspaceCommand,
        *,
        actor_id: str,
    ) -> str:
        grant_id = uuid4().hex
        with self.transaction() as conn:
            binding_row = conn.execute(
                text(
                    """
                    SELECT to_jsonb(binding) AS binding, NOW() AS observed_now
                    FROM host_runtime_bindings AS binding
                    WHERE binding.id = :binding_id
                      AND binding.generation = :binding_generation
                    FOR UPDATE OF binding
                    """
                ),
                command.model_dump(
                    include={"binding_id", "binding_generation"}
                ),
            ).fetchone()
            if binding_row is None:
                raise ValueError("host_grant_binding_generation_mismatch")
            attestation_row = conn.execute(
                text(
                    """
                    SELECT to_jsonb(attestation) AS attestation
                    FROM host_runtime_attestations AS attestation
                    WHERE attestation.binding_id = :binding_id
                    ORDER BY attestation.revision DESC
                    LIMIT 1
                    FOR SHARE
                    """
                ),
                {"binding_id": command.binding_id},
            ).fetchone()
            binding_payload = self.deserialize_json(
                binding_row.binding,
                default=None,
            )
            attestation_payload = self.deserialize_json(
                attestation_row.attestation if attestation_row else None,
                default=None,
            )
            if not isinstance(binding_payload, dict):
                raise ValueError("host_grant_binding_projection_invalid")
            if isinstance(attestation_payload, dict):
                binding_payload = {
                    **binding_payload,
                    "attestation": attestation_payload,
                }
            binding = binding_from_record(binding_payload)
            validate_grant_command(
                binding=binding,
                attestation=binding.attestation,
                command=command,
                now=binding_row.observed_now,
            )
            if binding.share_policy == "exclusive_workspace":
                conflicting = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM workspace_host_grants
                        WHERE binding_id = :binding_id
                          AND workspace_id <> :workspace_id
                          AND status = 'active'
                          AND expires_at > NOW()
                        LIMIT 1
                        """
                    ),
                    command.model_dump(
                        include={"binding_id", "workspace_id"}
                    ),
                ).fetchone()
                if conflicting is not None:
                    raise ValueError(
                        "host_grant_exclusive_workspace_conflict"
                    )
            conn.execute(
                text(
                    """
                    INSERT INTO workspace_host_grants
                        (id, workspace_id, binding_id, binding_generation,
                         operation, operation_args_sha256, policy_revision,
                         attestation_revision,
                         expires_at, status, provider_code, voice_profile_id,
                         reference_rights_revision, created_by)
                    VALUES
                        (:id, :workspace_id, :binding_id, :binding_generation,
                         :operation, :operation_args_sha256, :policy_revision,
                         :attestation_revision,
                         :expires_at, 'active', :provider_code,
                         :voice_profile_id, :reference_rights_revision,
                         :created_by)
                    """
                ),
                {
                    **command.model_dump(mode="json"),
                    "id": grant_id,
                    "created_by": actor_id,
                },
            )
            self._append_receipt(
                conn,
                binding_id=command.binding_id,
                generation=command.binding_generation,
                kind="granted",
                actor_id=actor_id,
                payload={
                    "grant_id": grant_id,
                    "workspace_id": command.workspace_id,
                    "operation": command.operation,
                    "operation_args_sha256": command.operation_args_sha256,
                    "policy_revision": command.policy_revision,
                    "attestation_revision": command.attestation_revision,
                },
            )
        return grant_id

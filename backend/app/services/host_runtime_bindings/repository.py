"""Bounded PostgreSQL primitives for host bindings, attestations, and grants."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .contracts import (
    AttestBindingCommand,
    DeclareBindingCommand,
    MaterializationReceiptCommand,
)
from .grant_repository import HostRuntimeGrantRepositoryMixin
from .lifecycle_repository import HostRuntimeLifecycleRepositoryMixin
from .state_machine import FINALIZER, next_generation


class HostRuntimeBindingRepository(
    HostRuntimeLifecycleRepositoryMixin,
    HostRuntimeGrantRepositoryMixin,
    PostgresStoreBase,
):
    def declare_binding(
        self,
        command: DeclareBindingCommand,
        *,
        actor_id: str,
    ) -> str:
        binding_id = uuid4().hex
        with self.transaction() as conn:
            current = conn.execute(
                text(
                    """
                    SELECT id, generation
                    FROM host_runtime_bindings
                    WHERE device_id = :device_id
                      AND capability_code = :capability_code
                      AND requirement_code = :requirement_code
                    FOR UPDATE
                    """
                ),
                command.model_dump(
                    include={
                        "device_id",
                        "capability_code",
                        "requirement_code",
                    }
                ),
            ).fetchone()
            current_generation = int(current.generation) if current else 0
            generation = next_generation(
                current_generation=current_generation,
                expected_generation=command.expected_generation,
            )
            values = {
                **command.model_dump(mode="json"),
                "id": current.id if current else binding_id,
                "generation": generation,
                "operations": self.serialize_json(command.operations),
                "permission_classes": self.serialize_json(
                    command.permission_classes
                ),
                "finalizers": self.serialize_json([FINALIZER]),
            }
            if current is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO host_runtime_bindings
                            (id, device_id, capability_code, requirement_code,
                            capability_version, runtime_digest,
                             host_assets_digest, entrypoint,
                             entrypoint_digest, desired_state, generation,
                             share_policy, operations, permission_classes,
                             resource_lane, finalizers)
                        VALUES
                            (:id, :device_id, :capability_code,
                             :requirement_code, :capability_version,
                             :runtime_digest, :host_assets_digest, :entrypoint,
                             :entrypoint_digest, 'declared',
                             :generation, :share_policy,
                             CAST(:operations AS jsonb),
                             CAST(:permission_classes AS jsonb),
                             :resource_lane, CAST(:finalizers AS jsonb))
                        """
                    ),
                    values,
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE host_runtime_bindings
                        SET capability_version = :capability_version,
                            runtime_digest = :runtime_digest,
                            host_assets_digest = :host_assets_digest,
                            entrypoint = :entrypoint,
                            entrypoint_digest = :entrypoint_digest,
                            desired_state = 'declared',
                            generation = :generation,
                            share_policy = :share_policy,
                            operations = CAST(:operations AS jsonb),
                            permission_classes =
                                CAST(:permission_classes AS jsonb),
                            resource_lane = :resource_lane,
                            materialized_root = NULL,
                            installed_tree_digest = NULL,
                            finalizers = CAST(:finalizers AS jsonb),
                            updated_at = NOW()
                        WHERE id = :id
                        """
                    ),
                    values,
                )
            self._append_receipt(
                conn,
                binding_id=values["id"],
                generation=generation,
                kind="declared",
                actor_id=actor_id,
                payload={
                    "runtime_digest": command.runtime_digest,
                    "host_assets_digest": command.host_assets_digest,
                },
            )
            return str(values["id"])

    def record_materialization(
        self,
        command: MaterializationReceiptCommand,
        *,
        actor_id: str,
    ) -> None:
        with self.transaction() as conn:
            updated = conn.execute(
                text(
                    """
                    UPDATE host_runtime_bindings
                    SET desired_state = 'materialized',
                        materialized_root = :materialized_root,
                        installed_tree_digest = :installed_tree_digest,
                        updated_at = NOW()
                    WHERE id = :binding_id
                      AND generation = :generation
                      AND runtime_digest = :runtime_digest
                      AND host_assets_digest = :host_assets_digest
                      AND desired_state IN ('declared','materialized')
                    RETURNING id
                    """
                ),
                command.model_dump(mode="json"),
            ).fetchone()
            if updated is None:
                raise ValueError("host_binding_materialization_causal_mismatch")
            self._append_receipt(
                conn,
                binding_id=command.binding_id,
                generation=command.generation,
                kind="materialized",
                actor_id=actor_id,
                payload=command.model_dump(
                    mode="json",
                    exclude={"binding_id", "materialized_root"},
                ),
            )

    def record_attestation(
        self,
        command: AttestBindingCommand,
        *,
        actor_id: str,
    ) -> int:
        with self.transaction() as conn:
            binding = conn.execute(
                text(
                    """
                    SELECT generation, runtime_digest, desired_state
                    FROM host_runtime_bindings
                    WHERE id = :binding_id
                    FOR UPDATE
                    """
                ),
                {"binding_id": command.binding_id},
            ).fetchone()
            if (
                binding is None
                or int(binding.generation) != command.generation
                or binding.runtime_digest != command.runtime_digest
                or binding.desired_state not in ("materialized", "active", "degraded")
            ):
                raise ValueError("host_binding_attestation_causal_mismatch")
            revision = int(
                conn.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(revision), 0) + 1
                        FROM host_runtime_attestations
                        WHERE binding_id = :binding_id
                        """
                    ),
                    {"binding_id": command.binding_id},
                ).scalar_one()
            )
            ready = all(
                condition.status == "true"
                for condition in command.conditions
            )
            conn.execute(
                text(
                    """
                    INSERT INTO host_runtime_attestations
                        (id, binding_id, revision, observed_generation,
                         runtime_digest, executor_identity_digest,
                         permission_revision, conditions, observed_at)
                    VALUES
                        (:id, :binding_id, :revision, :generation,
                         :runtime_digest, :executor_identity_digest,
                         :permission_revision, CAST(:conditions AS jsonb),
                         :observed_at)
                    """
                ),
                {
                    **command.model_dump(mode="json", exclude={"conditions"}),
                    "id": uuid4().hex,
                    "revision": revision,
                    "conditions": self.serialize_json(
                        [
                            condition.model_dump(mode="json")
                            for condition in command.conditions
                        ]
                    ),
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_bindings
                    SET desired_state = :desired_state, updated_at = NOW()
                    WHERE id = :binding_id
                    """
                ),
                {
                    "binding_id": command.binding_id,
                    "desired_state": "active" if ready else "degraded",
                },
            )
            self._append_receipt(
                conn,
                binding_id=command.binding_id,
                generation=command.generation,
                kind="attested",
                actor_id=actor_id,
                payload={
                    "attestation_revision": revision,
                    "ready": ready,
                    "runtime_digest": command.runtime_digest,
                },
            )
            return revision

    def revoke_grant(self, grant_id: str, *, actor_id: str) -> None:
        with self.transaction() as conn:
            grant = conn.execute(
                text(
                    """
                    UPDATE workspace_host_grants
                    SET status = 'revoked', revoked_at = NOW()
                    WHERE id = :grant_id AND status = 'active'
                    RETURNING binding_id, binding_generation, workspace_id,
                              operation
                    """
                ),
                {"grant_id": grant_id},
            ).fetchone()
            if grant is None:
                raise ValueError("workspace_host_grant_not_active")
            self._append_receipt(
                conn,
                binding_id=grant.binding_id,
                generation=int(grant.binding_generation),
                kind="revoked",
                actor_id=actor_id,
                payload={
                    "grant_id": grant_id,
                    "workspace_id": grant.workspace_id,
                    "operation": grant.operation,
                },
            )

    def load_effective_records(
        self,
        *,
        workspace_id: str,
        capability_code: str,
        requirement_code: str,
        operation: str,
    ) -> dict[str, Any]:
        """Load one binding, latest attestation, and grant in one statement."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        to_jsonb(binding) AS binding,
                        to_jsonb(attestation) AS attestation,
                        to_jsonb(host_grant) AS host_grant
                    FROM host_runtime_bindings AS binding
                    LEFT JOIN LATERAL (
                        SELECT revision, observed_generation, runtime_digest,
                               executor_identity_digest, permission_revision,
                               conditions, observed_at
                        FROM host_runtime_attestations
                        WHERE binding_id = binding.id
                        ORDER BY revision DESC
                        LIMIT 1
                    ) AS attestation ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT id, workspace_id, binding_id,
                               binding_generation, operation,
                               operation_args_sha256, policy_revision,
                               attestation_revision, expires_at, status,
                               provider_code, voice_profile_id,
                               reference_rights_revision
                        FROM workspace_host_grants
                        WHERE workspace_id = :workspace_id
                          AND binding_id = binding.id
                          AND operation = :operation
                        ORDER BY policy_revision DESC
                        LIMIT 1
                    ) AS host_grant ON TRUE
                    WHERE binding.capability_code = :capability_code
                      AND binding.requirement_code = :requirement_code
                      AND binding.desired_state <> 'retired'
                    ORDER BY binding.updated_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "capability_code": capability_code,
                    "requirement_code": requirement_code,
                    "operation": operation,
                },
            ).fetchone()
        if row is None:
            return {"binding": None, "attestation": None, "grant": None}
        return {
            "binding": self.deserialize_json(row.binding, default=None),
            "attestation": self.deserialize_json(
                row.attestation,
                default=None,
            ),
            "grant": self.deserialize_json(row.host_grant, default=None),
        }

    def load_binding_record(self, binding_id: str) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        to_jsonb(binding) AS binding,
                        to_jsonb(attestation) AS attestation
                    FROM host_runtime_bindings AS binding
                    LEFT JOIN LATERAL (
                        SELECT revision, observed_generation, runtime_digest,
                               executor_identity_digest, permission_revision,
                               conditions, observed_at
                        FROM host_runtime_attestations
                        WHERE binding_id = binding.id
                        ORDER BY revision DESC
                        LIMIT 1
                    ) AS attestation ON TRUE
                    WHERE binding.id = :binding_id
                    """
                ),
                {"binding_id": binding_id},
            ).fetchone()
        if row is None:
            return None
        binding = self.deserialize_json(row.binding, default=None)
        attestation = self.deserialize_json(row.attestation, default=None)
        if isinstance(binding, dict) and isinstance(attestation, dict):
            return {**binding, "attestation": attestation}
        return binding if isinstance(binding, dict) else None

    def _append_receipt(
        self,
        conn: Any,
        *,
        binding_id: str,
        generation: int,
        kind: str,
        actor_id: str,
        payload: dict[str, Any],
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO host_runtime_receipts
                    (id, binding_id, generation, kind, payload, actor_id)
                VALUES
                    (:id, :binding_id, :generation, :kind,
                     CAST(:payload AS jsonb), :actor_id)
                """
            ),
            {
                "id": uuid4().hex,
                "binding_id": binding_id,
                "generation": generation,
                "kind": kind,
                "payload": self.serialize_json(payload),
                "actor_id": actor_id,
            },
        )

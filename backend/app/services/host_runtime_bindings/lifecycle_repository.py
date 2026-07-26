"""Transaction-locked retirement and finalizer persistence for host bindings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .contracts import (
    FinalizeBindingRetirementCommand,
    RequestBindingRetirementCommand,
)
from .state_machine import FINALIZER, transition_binding


class HostRuntimeLifecycleRepositoryMixin:
    """Persist retirement through one causal state/finalizer transaction."""

    def request_retirement(
        self,
        command: RequestBindingRetirementCommand,
        *,
        actor_id: str,
    ) -> None:
        with self.transaction() as conn:
            binding = self._lock_binding_for_lifecycle(
                conn,
                binding_id=command.binding_id,
                generation=command.generation,
            )
            active_grant_count = self._active_grant_count(
                conn,
                binding_id=command.binding_id,
            )
            desired_state, finalizers = transition_binding(
                current_state=binding.desired_state,
                requested_state="retiring",
                active_grant_count=active_grant_count,
                supervisor_cleanup_terminal=False,
            )
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_bindings
                    SET desired_state = :desired_state,
                        finalizers = CAST(:finalizers AS jsonb),
                        updated_at = NOW()
                    WHERE id = :binding_id AND generation = :generation
                    """
                ),
                {
                    "binding_id": command.binding_id,
                    "generation": command.generation,
                    "desired_state": desired_state,
                    "finalizers": self.serialize_json(list(finalizers)),
                },
            )
            self._append_receipt(
                conn,
                binding_id=command.binding_id,
                generation=command.generation,
                kind="retiring",
                actor_id=actor_id,
                payload={
                    "reason": command.reason,
                    "active_grant_count": active_grant_count,
                    "finalizer": FINALIZER,
                },
            )

    def finalize_retirement(
        self,
        command: FinalizeBindingRetirementCommand,
        *,
        actor_id: str,
    ) -> None:
        with self.transaction() as conn:
            binding = self._lock_binding_for_lifecycle(
                conn,
                binding_id=command.binding_id,
                generation=command.generation,
            )
            active_grant_count = self._active_grant_count(
                conn,
                binding_id=command.binding_id,
            )
            desired_state, finalizers = transition_binding(
                current_state=binding.desired_state,
                requested_state="retired",
                active_grant_count=active_grant_count,
                supervisor_cleanup_terminal=command.supervisor_cleanup_terminal,
            )
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_bindings
                    SET desired_state = :desired_state,
                        finalizers = CAST(:finalizers AS jsonb),
                        updated_at = NOW()
                    WHERE id = :binding_id AND generation = :generation
                    """
                ),
                {
                    "binding_id": command.binding_id,
                    "generation": command.generation,
                    "desired_state": desired_state,
                    "finalizers": self.serialize_json(list(finalizers)),
                },
            )
            self._append_receipt(
                conn,
                binding_id=command.binding_id,
                generation=command.generation,
                kind="retired",
                actor_id=actor_id,
                payload={
                    "active_grant_count": active_grant_count,
                    "supervisor_cleanup_terminal": True,
                    "finalizers": [],
                },
            )

    @staticmethod
    def _lock_binding_for_lifecycle(
        conn: Any,
        *,
        binding_id: str,
        generation: int,
    ) -> Any:
        binding = conn.execute(
            text(
                """
                SELECT id, generation, desired_state, finalizers
                FROM host_runtime_bindings
                WHERE id = :binding_id AND generation = :generation
                FOR UPDATE
                """
            ),
            {"binding_id": binding_id, "generation": generation},
        ).fetchone()
        if binding is None:
            raise ValueError("host_binding_lifecycle_generation_mismatch")
        return binding

    @staticmethod
    def _active_grant_count(conn: Any, *, binding_id: str) -> int:
        return int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM workspace_host_grants
                    WHERE binding_id = :binding_id
                      AND status = 'active'
                      AND expires_at > NOW()
                    """
                ),
                {"binding_id": binding_id},
            ).scalar_one()
        )

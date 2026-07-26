"""Action-triggered permit issuance with one bounded attestation refresh."""

from __future__ import annotations

import asyncio
from datetime import datetime

from backend.app.services.device_node_host_runtime_client import (
    DeviceNodeHostRuntimeClient,
)
from backend.app.services.host_runtime_bindings.contracts import (
    HostOperation,
    HostRuntimeExecutionPermit,
)
from backend.app.services.host_runtime_bindings.facade import (
    HostRuntimeBindingFacade,
)


REFRESHABLE_BLOCKERS = frozenset(
    {
        "binding_not_active",
        "attestation_missing",
        "attestation_generation_mismatch",
        "attestation_digest_mismatch",
        "attestation_stale",
        "attestation_condition_not_ready",
    }
)


class HostRuntimeExecutionPermitCoordinator:
    """Issue normally; refresh Device Node attestation once only when needed."""

    def __init__(
        self,
        *,
        facade: HostRuntimeBindingFacade | None = None,
        device_node_client: DeviceNodeHostRuntimeClient | None = None,
    ) -> None:
        self.facade = facade or HostRuntimeBindingFacade()
        self.device_node_client = (
            device_node_client or DeviceNodeHostRuntimeClient()
        )

    async def issue(
        self,
        *,
        workspace_id: str,
        capability_code: str,
        requirement_code: str,
        operation: HostOperation,
        operation_args: list[str],
        ttl_seconds: int,
        actor_id: str,
        now: datetime | None = None,
    ) -> HostRuntimeExecutionPermit:
        arguments = {
            "workspace_id": workspace_id,
            "capability_code": capability_code,
            "requirement_code": requirement_code,
            "operation": operation,
            "operation_args": operation_args,
            "ttl_seconds": ttl_seconds,
            "now": now,
        }
        try:
            return await asyncio.to_thread(
                self.facade.issue_execution_permit,
                **arguments,
            )
        except ValueError as initial_error:
            admission = await asyncio.to_thread(
                self.facade.resolve_effective_admission,
                workspace_id=workspace_id,
                capability_code=capability_code,
                requirement_code=requirement_code,
                operation=operation,
                now=now,
            )
            blockers = frozenset(admission.blockers)
            if (
                not admission.binding_id
                or not blockers
                or not blockers.issubset(REFRESHABLE_BLOCKERS)
            ):
                raise initial_error
            binding = await asyncio.to_thread(
                self.facade.get_binding,
                admission.binding_id,
            )
            command = await self.device_node_client.attest_binding(binding)
            await asyncio.to_thread(
                self.facade.record_attestation,
                command,
                actor_id=actor_id,
            )
            return await asyncio.to_thread(
                self.facade.issue_execution_permit,
                **arguments,
            )


__all__ = [
    "HostRuntimeExecutionPermitCoordinator",
    "REFRESHABLE_BLOCKERS",
]

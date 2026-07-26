"""Single root admission facade for Local Core execution entrypoints."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from backend.app.services.workspace_groups.snapshot_service import (
    WorkspaceGroupSnapshotService,
)
from backend.app.services.workspace_product_configuration.facade import (
    WorkspaceProductConfigurationFacade,
)

from .contracts import (
    AdmissionAvailability,
    AdmissionDenied,
    RootAdmissionRequest,
    RootAdmissionResult,
    RootPrincipalEvidence,
)
from .deployment_gate import DeploymentGate
from .execution_snapshot import build_execution_snapshot
from .external_execution_adapter import (
    ExternalAuthorizationDenied,
    ExternalAuthorizationUnavailable,
    ExternalExecutionAuthorizationAdapter,
)
from .external_execution_contracts import (
    ExternalCapabilityRef,
    ExternalExecutionAuthorizationRequest,
    ExternalPackRef,
)
from .host_readiness import ProductResolution, resolve_product
from .outcome_metrics import record_shadow_outcome
from .remote_entry_gate import remote_entry_permitted


class WorkspaceCapabilityAdmissionFacade:
    """Resolve every mutable governance source once at root admission."""

    def __init__(
        self,
        *,
        workspace_product_facade: (
            WorkspaceProductConfigurationFacade | None
        ) = None,
        deployment_gate: DeploymentGate | None = None,
        topology_snapshot_service: (
            WorkspaceGroupSnapshotService | None
        ) = None,
        external_adapter: (
            ExternalExecutionAuthorizationAdapter | None
        ) = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._workspace_products = (
            workspace_product_facade
            or WorkspaceProductConfigurationFacade()
        )
        self._deployment = deployment_gate or DeploymentGate()
        self._topology_snapshots = (
            topology_snapshot_service or WorkspaceGroupSnapshotService()
        )
        self._external = (
            external_adapter or ExternalExecutionAuthorizationAdapter()
        )
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def admit_root(
        self,
        request: RootAdmissionRequest,
    ) -> RootAdmissionResult:
        source = await asyncio.to_thread(
            self._workspace_products.resolve_admission_source,
            workspace_id=request.workspace_id,
            explicit_active_group_id=request.explicit_active_group_id,
            observed_topology_revision=request.observed_topology_revision,
            actor_user_id=request.actor_user_id,
            allowed_workspace_ids=request.allowed_workspace_ids,
            allowed_group_ids=request.allowed_group_ids,
        )
        resolution = resolve_product(source, request)
        availability, diagnostics = self._local_outcome(
            source.snapshot.configuration_errors,
            resolution,
        )
        mode = source.snapshot.workspace_admission_mode
        if mode == "shadow":
            record_shadow_outcome(availability)
        if mode == "enforced" and availability != "available":
            raise AdmissionDenied(availability)
        if not remote_entry_permitted(request):
            raise AdmissionDenied("remote_not_exposed")

        deployment = await asyncio.to_thread(
            self._deployment.evaluate,
            wpcs=source.snapshot,
            pcs_id=resolution.pcs_id,
            pcs_version=resolution.pcs_version,
            product_surface_id=(
                resolution.product_surface_id
                or request.product_surface_id
                or "legacy.unclassified"
            ),
        )
        if not deployment.permitted:
            raise AdmissionDenied("deployment_not_permitted")

        topology_snapshot = None
        if source.active_group_context is not None:
            topology_snapshot = await asyncio.to_thread(
                self._topology_snapshots.get_or_create,
                source.active_group_context,
                actor_user_id=request.actor_user_id,
            )

        external_decision = None
        if request.execution_backend == "external_provider":
            if topology_snapshot is None or resolution.product is None:
                raise AdmissionDenied(
                    "external_authorization_unavailable"
                )
            external_request = self._external_request(
                request=request,
                resolution=resolution,
                source_runtime_id=source.snapshot.source_runtime_id,
                wpcs_hash=source.snapshot.snapshot_hash,
                catalog_hash=source.snapshot.catalog_hash,
                topology_snapshot_id=topology_snapshot.id,
                topology_snapshot_hash=topology_snapshot.content_hash,
                deployment_mode=deployment.ceiling.mode,
                dce_hash=deployment.ceiling.envelope_hash,
            )
            try:
                external_decision = await self._external.authorize_root(
                    external_request
                )
            except ExternalAuthorizationUnavailable as exc:
                raise AdmissionDenied(
                    "external_authorization_unavailable"
                ) from exc
            except ExternalAuthorizationDenied:
                raise

        admitted_at = self._now()
        if admitted_at.tzinfo is None:
            raise ValueError("admission_clock_must_be_timezone_aware")
        snapshot = build_execution_snapshot(
            {
                "source_runtime_id": source.snapshot.source_runtime_id,
                "workspace_id": request.workspace_id,
                "active_group_id": (
                    topology_snapshot.group_id
                    if topology_snapshot is not None
                    else None
                ),
                "topology_revision": (
                    topology_snapshot.group_revision
                    if topology_snapshot is not None
                    else None
                ),
                "topology_snapshot_id": (
                    topology_snapshot.id
                    if topology_snapshot is not None
                    else None
                ),
                "topology_snapshot_hash": (
                    topology_snapshot.content_hash
                    if topology_snapshot is not None
                    else None
                ),
                "wpcs_hash": source.snapshot.snapshot_hash,
                "catalog_hash": source.snapshot.catalog_hash,
                "admission_mode": mode,
                "pcs_id": resolution.pcs_id,
                "pcs_version": resolution.pcs_version,
                "product_surface_id": (
                    resolution.product_surface_id
                    or request.product_surface_id
                    or "legacy.unclassified"
                ),
                "selector_kind": request.selector_kind,
                "selector_key": request.selector_key,
                "operation_type": request.operation_type,
                "entry": request.entry,
                "execution_backend": request.execution_backend,
                "deployment_mode": deployment.ceiling.mode,
                "deployment_state_revision": (
                    deployment.ceiling.state_revision
                ),
                "deployment_envelope_revision": (
                    deployment.ceiling.envelope_revision
                ),
                "dce_hash": deployment.ceiling.envelope_hash,
                "availability": availability,
                "diagnostics": sorted(set(diagnostics)),
                "external_decision_id": (
                    external_decision.decision_id
                    if external_decision is not None
                    else None
                ),
                "external_decision_issuer": (
                    external_decision.issuer
                    if external_decision is not None
                    else None
                ),
                "external_decision_expires_at": (
                    external_decision.expires_at
                    if external_decision is not None
                    else None
                ),
                "provider_token_id": (
                    external_decision.provider.token_id
                    if external_decision is not None
                    and external_decision.provider is not None
                    else None
                ),
                "trace_id": request.trace_id,
                "root_execution_id": request.root_execution_id,
                "admitted_at": admitted_at,
            }
        )
        return RootAdmissionResult(
            snapshot=snapshot,
            external_decision=external_decision,
            active_group_context=source.active_group_context,
            topology_snapshot=topology_snapshot,
            principal_evidence=RootPrincipalEvidence(
                workspace_id=request.workspace_id,
                actor_user_id=request.actor_user_id,
                allowed_workspace_ids=tuple(
                    sorted(set(request.allowed_workspace_ids))
                ),
                allowed_group_ids=tuple(
                    sorted(set(request.allowed_group_ids))
                ),
                workspace_owner_user_id=source.workspace_owner_user_id,
                group_owner_user_id=(
                    source.active_group_context.topology.owner_user_id
                    if source.active_group_context is not None
                    else None
                ),
            ),
        )

    @staticmethod
    def _local_outcome(
        configuration_errors: list[str],
        resolution: ProductResolution,
    ) -> tuple[AdmissionAvailability, list[str]]:
        diagnostics = list(configuration_errors)
        if configuration_errors:
            return "configuration_conflict", diagnostics
        if not resolution.configured:
            diagnostics.append("product_surface_not_configured")
            return "not_configured", diagnostics
        if not resolution.selector_permitted:
            diagnostics.append("selector_not_in_product_surface")
            return "capability_not_permitted", diagnostics
        if not resolution.host_ready:
            diagnostics.append("product_pack_closure_not_ready")
            return "not_installed", diagnostics
        return "available", diagnostics

    def _external_request(
        self,
        *,
        request: RootAdmissionRequest,
        resolution: ProductResolution,
        source_runtime_id: str,
        wpcs_hash: str,
        catalog_hash: str,
        topology_snapshot_id: str,
        topology_snapshot_hash: str,
        deployment_mode: str,
        dce_hash: str | None,
    ) -> ExternalExecutionAuthorizationRequest:
        if resolution.product is None:
            raise AdmissionDenied("external_authorization_unavailable")
        packs = sorted(
            (
                ExternalPackRef.model_validate(item)
                for item in resolution.product.get("pack_closure", [])
            ),
            key=lambda item: item.canonical_ref,
        )
        return ExternalExecutionAuthorizationRequest(
            source_runtime_id=source_runtime_id,
            workspace_id=request.workspace_id,
            active_group_id=request.explicit_active_group_id or "",
            topology_snapshot_id=topology_snapshot_id,
            topology_snapshot_hash=topology_snapshot_hash,
            wpcs_hash=wpcs_hash,
            catalog_hash=catalog_hash,
            product_surface_id=(
                resolution.product_surface_id
                or request.product_surface_id
                or "legacy.unclassified"
            ),
            exact_capability_closure=[
                ExternalCapabilityRef(
                    capability_key=request.selector_key,
                    operation_type=request.operation_type,
                )
            ],
            exact_pack_closure=packs,
            deployment_mode=deployment_mode,
            dce_hash=dce_hash,
            trace_id=request.trace_id,
            root_execution_id=request.root_execution_id,
            request_deadline=self._now() + timedelta(seconds=10),
        )

"""Single writer and effective reader for workspace product configuration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Sequence

from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
)
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade
from backend.app.services.workspace_groups.snapshot_service import (
    topology_content_hash,
)

from .catalog_artifact import verify_catalog_artifact
from .contracts import (
    AdmissionConfigurationSource,
    CatalogImportResult,
    ProductAssignment,
    ReplaceScopeCommand,
    ScopeKind,
    WorkspaceCapabilitySetSnapshot,
)
from .errors import (
    ActiveCatalogMissingError,
    CatalogRevisionConflictError,
    ScopeAccessError,
    TopologyRevisionConflictError,
    TopologyRevisionRequiredError,
    WorkspaceProductConfigurationError,
)
from .projection import build_snapshot
from .repository import WorkspaceProductConfigurationRepository
from .runtime_identity import source_runtime_id


class WorkspaceProductConfigurationFacade:
    """The only application owner for catalog import, scope CAS, and WPCS."""

    def __init__(
        self,
        *,
        repository: WorkspaceProductConfigurationRepository | None = None,
        workspace_group_facade: WorkspaceGroupFacade | None = None,
        runtime_id: str | None = None,
    ):
        self.repository = (
            repository or WorkspaceProductConfigurationRepository()
        )
        self.workspace_group_facade = (
            workspace_group_facade or WorkspaceGroupFacade()
        )
        self.runtime_id = runtime_id or source_runtime_id()

    def import_catalog(
        self,
        artifact_payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> CatalogImportResult:
        artifact = verify_catalog_artifact(artifact_payload)
        imported = self.repository.import_catalog(
            artifact,
            actor_user_id=actor_user_id,
        )
        return CatalogImportResult(
            artifact_hash=artifact.artifact_hash,
            catalog_hash=artifact.catalog_hash,
            source_commit=artifact.source_commit,
            compiler_version=artifact.compiler_version,
            imported=imported,
        )

    def resolve_snapshot(
        self,
        *,
        workspace_id: str,
        explicit_active_group_id: str | None,
        observed_topology_revision: int | None,
        actor_user_id: str,
        allowed_workspace_ids: Sequence[str] = (),
        allowed_group_ids: Sequence[str] = (),
    ) -> WorkspaceCapabilitySetSnapshot:
        return self.resolve_admission_source(
            workspace_id=workspace_id,
            explicit_active_group_id=explicit_active_group_id,
            observed_topology_revision=observed_topology_revision,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
            allowed_workspace_ids=allowed_workspace_ids,
        ).snapshot

    def resolve_admission_source(
        self,
        *,
        workspace_id: str,
        explicit_active_group_id: str | None,
        observed_topology_revision: int | None,
        actor_user_id: str,
        allowed_workspace_ids: Sequence[str] = (),
        allowed_group_ids: Sequence[str] = (),
    ) -> AdmissionConfigurationSource:
        """Resolve WPCS, active topology, and catalog products in one DB read."""
        self._require_workspace_access(workspace_id, allowed_workspace_ids)
        context = self._resolve_group_context(
            workspace_id=workspace_id,
            explicit_active_group_id=explicit_active_group_id,
            observed_topology_revision=observed_topology_revision,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        state = self.repository.load_effective_state(
            workspace_id=workspace_id,
            group_id=context.group_id if context else None,
        )
        catalog = self._active_catalog(state)
        products = catalog.get("products")
        if not isinstance(products, list):
            raise ActiveCatalogMissingError()
        return AdmissionConfigurationSource(
            snapshot=self._build_snapshot(
                workspace_id=workspace_id,
                context=context,
                state=state,
                readiness=state["readiness"],
                actor_user_id=actor_user_id,
            ),
            active_group_context=context,
            catalog_products=tuple(
                deepcopy(product)
                for product in products
                if isinstance(product, dict)
            ),
            workspace_owner_user_id=state.get("workspace_owner_user_id"),
        )

    def replace_scope(
        self,
        *,
        scope_kind: ScopeKind,
        scope_id: str,
        workspace_id: str,
        explicit_active_group_id: str | None,
        observed_topology_revision: int | None,
        command: ReplaceScopeCommand,
        actor_user_id: str,
        allowed_workspace_ids: Sequence[str] = (),
        allowed_group_ids: Sequence[str] = (),
    ) -> WorkspaceCapabilitySetSnapshot:
        """CAS replace and return committed WPCS without a follow-up GET."""
        self._require_workspace_access(workspace_id, allowed_workspace_ids)
        if (
            explicit_active_group_id is not None
            and observed_topology_revision is None
        ):
            raise TopologyRevisionRequiredError()
        context = self._resolve_group_context(
            workspace_id=workspace_id,
            explicit_active_group_id=explicit_active_group_id,
            observed_topology_revision=observed_topology_revision,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        self._require_scope_access(
            scope_kind=scope_kind,
            scope_id=scope_id,
            workspace_id=workspace_id,
            context=context,
            actor_user_id=actor_user_id,
        )
        state = self.repository.load_effective_state(
            workspace_id=workspace_id,
            group_id=context.group_id if context else None,
        )
        catalog = self._active_catalog(state)
        if command.catalog_hash != state["catalog_hash"]:
            raise CatalogRevisionConflictError(
                expected_catalog_hash=command.catalog_hash,
                current_catalog_hash=state["catalog_hash"],
            )
        self._validate_assignments(command.assignments, catalog)
        mode = self._resolve_admission_mode(
            scope_kind=scope_kind,
            scope_id=scope_id,
            expected_revision=command.expected_revision,
            requested_mode=command.admission_mode,
            state=state,
        )
        committed = self.repository.replace_scope(
            scope_kind=scope_kind,
            scope_id=scope_id,
            expected_revision=command.expected_revision,
            catalog_hash=command.catalog_hash,
            admission_mode=mode,
            assignments=command.assignments,
            actor_user_id=actor_user_id,
        )
        committed_state = self._replace_scope_projection(state, committed)
        return self._build_snapshot(
            workspace_id=workspace_id,
            context=context,
            state=committed_state,
            readiness=state["readiness"],
            actor_user_id=actor_user_id,
        )

    def _resolve_group_context(
        self,
        *,
        workspace_id: str,
        explicit_active_group_id: str | None,
        observed_topology_revision: int | None,
        actor_user_id: str,
        allowed_group_ids: Sequence[str],
    ) -> ActiveWorkspaceGroupContext | None:
        context = self.workspace_group_facade.resolve_context(
            active_group_id=explicit_active_group_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        if (
            context
            and observed_topology_revision is not None
            and observed_topology_revision != context.revision
        ):
            raise TopologyRevisionConflictError(
                expected_revision=observed_topology_revision,
                actual_revision=context.revision,
            )
        return context

    @staticmethod
    def _require_workspace_access(
        workspace_id: str,
        allowed_workspace_ids: Sequence[str],
    ) -> None:
        if workspace_id not in set(allowed_workspace_ids):
            raise ScopeAccessError(workspace_id)

    @staticmethod
    def _require_scope_access(
        *,
        scope_kind: ScopeKind,
        scope_id: str,
        workspace_id: str,
        context: ActiveWorkspaceGroupContext | None,
        actor_user_id: str,
    ) -> None:
        if scope_kind == "workspace":
            if scope_id != workspace_id:
                raise ScopeAccessError(scope_id)
            return
        if (
            context is None
            or context.group_id != scope_id
            or context.topology.owner_user_id != actor_user_id
        ):
            raise ScopeAccessError(scope_id)

    @staticmethod
    def _active_catalog(state: dict[str, Any]) -> dict[str, Any]:
        artifact = state.get("artifact")
        catalog = artifact.get("catalog") if isinstance(artifact, dict) else None
        if not state.get("catalog_hash") or not isinstance(catalog, dict):
            raise ActiveCatalogMissingError()
        return catalog

    @staticmethod
    def _validate_assignments(
        assignments: list[ProductAssignment],
        catalog: dict[str, Any],
    ) -> None:
        valid = {
            (product["pcs_id"], product["version"])
            for product in catalog["products"]
        }
        invalid = [
            f"{assignment.pcs_id}@{assignment.pcs_version}"
            for assignment in assignments
            if (assignment.pcs_id, assignment.pcs_version) not in valid
        ]
        if invalid:
            raise WorkspaceProductConfigurationError(
                "unknown_product_assignments:" + ",".join(sorted(invalid))
            )

    @staticmethod
    def _resolve_admission_mode(
        *,
        scope_kind: ScopeKind,
        scope_id: str,
        expected_revision: int,
        requested_mode: str | None,
        state: dict[str, Any],
    ) -> str | None:
        if scope_kind == "workspace_group":
            if requested_mode is not None:
                raise WorkspaceProductConfigurationError(
                    "group_scope_cannot_set_admission_mode"
                )
            return None
        existing = next(
            (
                row
                for row in state["scopes"]
                if row["scope_kind"] == "workspace"
                and row["scope_id"] == scope_id
            ),
            None,
        )
        if expected_revision == 0:
            if requested_mode not in {None, "configuration_only"}:
                raise WorkspaceProductConfigurationError(
                    "first_workspace_save_must_be_configuration_only"
                )
            return "configuration_only"
        if existing is None:
            return requested_mode or "configuration_only"
        return requested_mode or existing["admission_mode"]

    def _build_snapshot(
        self,
        *,
        workspace_id: str,
        context: ActiveWorkspaceGroupContext | None,
        state: dict[str, Any],
        readiness: dict[str, dict[str, Any]],
        actor_user_id: str,
    ) -> WorkspaceCapabilitySetSnapshot:
        return build_snapshot(
            source_runtime_id=self.runtime_id,
            workspace_id=workspace_id,
            group_context=context,
            topology_hash=topology_content_hash(context) if context else None,
            state=state,
            readiness=readiness,
            workspace_editable=True,
            group_editable=bool(
                context
                and context.topology.owner_user_id == actor_user_id
            ),
        )

    @staticmethod
    def _replace_scope_projection(
        state: dict[str, Any],
        committed: dict[str, Any],
    ) -> dict[str, Any]:
        updated = deepcopy(state)
        replacement = {
            **committed,
            "assignments": [
                assignment.model_dump()
                for assignment in committed["assignments"]
            ],
        }
        updated["scopes"] = [
            row
            for row in updated["scopes"]
            if (row["scope_kind"], row["scope_id"])
            != (committed["scope_kind"], committed["scope_id"])
        ]
        updated["scopes"].append(replacement)
        return updated

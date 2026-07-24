"""Build the compact WPCS projection from one bounded repository read."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
)

from .contracts import (
    AvailableProduct,
    EffectiveProductAssignment,
    ProductAssignment,
    ProductClosureSummary,
    ScopeConfiguration,
    WorkspaceCapabilitySetSnapshot,
)
from .errors import WorkspaceProductSnapshotLimitError


MAX_SNAPSHOT_BYTES = 64 * 1024


def build_snapshot(
    *,
    source_runtime_id: str,
    workspace_id: str,
    group_context: ActiveWorkspaceGroupContext | None,
    topology_hash: str | None,
    state: dict[str, Any],
    readiness: dict[str, dict[str, Any]],
    workspace_editable: bool,
    group_editable: bool,
) -> WorkspaceCapabilitySetSnapshot:
    catalog = state["artifact"]["catalog"]
    products = {
        (product["pcs_id"], product["version"]): product
        for product in catalog["products"]
    }
    scope_rows = {
        (row["scope_kind"], row["scope_id"]): row
        for row in state["scopes"]
    }
    workspace_row = scope_rows.get(("workspace", workspace_id))
    group_row = (
        scope_rows.get(("workspace_group", group_context.group_id))
        if group_context
        else None
    )
    scope_configurations = [
        _scope_projection(
            row=workspace_row,
            scope_kind="workspace",
            scope_id=workspace_id,
            editable=workspace_editable,
            absent_mode="legacy_unmanaged",
        )
    ]
    editable_scopes = ["workspace"] if workspace_editable else []
    if group_context:
        scope_configurations.append(
            _scope_projection(
                row=group_row,
                scope_kind="workspace_group",
                scope_id=group_context.group_id,
                editable=group_editable,
                absent_mode=None,
            )
        )
        if group_editable:
            editable_scopes.append("workspace_group")

    errors: list[str] = []
    for scope in scope_configurations:
        if scope.catalog_hash and scope.catalog_hash != state["catalog_hash"]:
            errors.append(
                f"scope_catalog_stale:{scope.scope_kind}:{scope.scope_id}"
            )
    available_products = [
        _available_product(product, readiness)
        for product in sorted(
            products.values(),
            key=lambda item: (item["pcs_id"], item["version"]),
        )
    ]
    effective_assignments = _effective_assignments(
        scopes=scope_configurations,
        products=products,
        readiness=readiness,
        errors=errors,
    )
    workspace_revision = scope_configurations[0].revision
    group_revision = (
        scope_configurations[1].revision
        if len(scope_configurations) > 1
        else 0
    )
    workspace_mode = (
        scope_configurations[0].admission_mode or "legacy_unmanaged"
    )
    payload = {
        "source_runtime_id": source_runtime_id,
        "workspace_id": workspace_id,
        "explicit_active_group_id": (
            group_context.group_id if group_context else None
        ),
        "topology_revision": group_context.revision if group_context else None,
        "topology_content_hash": topology_hash,
        "catalog_hash": state["catalog_hash"],
        "workspace_scope_revision": workspace_revision,
        "group_scope_revision": group_revision,
        "workspace_admission_mode": workspace_mode,
        "editable_scopes": editable_scopes,
        "scope_configurations": [
            scope.model_dump(mode="json") for scope in scope_configurations
        ],
        "available_products": [
            product.model_dump(mode="json") for product in available_products
        ],
        "effective_assignments": [
            assignment.model_dump(mode="json")
            for assignment in effective_assignments
        ],
        "configuration_errors": errors[:20],
    }
    snapshot_hash = sha256(_canonical_bytes(payload)).hexdigest()
    snapshot_payload = {**payload, "snapshot_hash": snapshot_hash}
    if len(_canonical_bytes(snapshot_payload)) + 1 > MAX_SNAPSHOT_BYTES:
        raise WorkspaceProductSnapshotLimitError()
    return WorkspaceCapabilitySetSnapshot.model_validate(snapshot_payload)


def _scope_projection(
    *,
    row: dict[str, Any] | None,
    scope_kind: str,
    scope_id: str,
    editable: bool,
    absent_mode: str | None,
) -> ScopeConfiguration:
    return ScopeConfiguration.model_validate(
        {
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "catalog_hash": row.get("catalog_hash") if row else None,
            "revision": int(row.get("revision") or 0) if row else 0,
            "admission_mode": (
                row.get("admission_mode") if row else absent_mode
            ),
            "assignments": row.get("assignments") if row else [],
            "editable": editable,
        }
    )


def _available_product(
    product: dict[str, Any],
    readiness: dict[str, dict[str, Any]],
) -> AvailableProduct:
    summary = _closure_summary(product, readiness)
    return AvailableProduct(
        pcs_id=product["pcs_id"],
        exact_version=product["version"],
        display_name=product["display_name"],
        outcome_summary=product["outcome_summary"],
        surface_ids=[
            surface["id"] for surface in product["product_surfaces"]
        ],
        closure_summary=summary,
    )


def _closure_summary(
    product: dict[str, Any],
    readiness: dict[str, dict[str, Any]],
) -> ProductClosureSummary:
    missing = disabled = mismatch = ready = 0
    for pack in product["pack_closure"]:
        installed = readiness.get(pack["code"])
        if installed is None:
            missing += 1
        elif not installed["enabled"]:
            disabled += 1
        elif installed["version"] != pack["version"]:
            mismatch += 1
        else:
            ready += 1
    return ProductClosureSummary(
        total_packs=len(product["pack_closure"]),
        exact_ready_packs=ready,
        missing_packs=missing,
        disabled_packs=disabled,
        version_mismatch_packs=mismatch,
    )


def _effective_assignments(
    *,
    scopes: list[ScopeConfiguration],
    products: dict[tuple[str, str], dict[str, Any]],
    readiness: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[EffectiveProductAssignment]:
    sources: dict[tuple[str, str], set[str]] = {}
    for scope in scopes:
        for assignment in scope.assignments:
            identity = (assignment.pcs_id, assignment.pcs_version)
            if identity not in products:
                errors.append(
                    f"assignment_not_in_active_catalog:"
                    f"{scope.scope_kind}:{assignment.pcs_id}@"
                    f"{assignment.pcs_version}"
                )
                continue
            sources.setdefault(identity, set()).add(scope.scope_kind)
    versions_by_product: dict[str, set[str]] = {}
    for pcs_id, pcs_version in sources:
        versions_by_product.setdefault(pcs_id, set()).add(pcs_version)
    conflicted_products = {
        pcs_id
        for pcs_id, versions in versions_by_product.items()
        if len(versions) > 1
    }
    for pcs_id in sorted(conflicted_products):
        errors.append(
            "assignment_version_conflict:"
            f"{pcs_id}:{','.join(sorted(versions_by_product[pcs_id]))}"
        )
    result = []
    for identity, configuration_sources in sorted(sources.items()):
        if identity[0] in conflicted_products:
            continue
        product = products[identity]
        summary = _closure_summary(product, readiness)
        result.append(
            EffectiveProductAssignment(
                pcs_id=identity[0],
                pcs_version=identity[1],
                product_surface_ids=[
                    surface["id"] for surface in product["product_surfaces"]
                ],
                configuration_sources=sorted(configuration_sources),
                host_ready=(
                    summary.exact_ready_packs == summary.total_packs
                ),
            )
        )
    return result


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

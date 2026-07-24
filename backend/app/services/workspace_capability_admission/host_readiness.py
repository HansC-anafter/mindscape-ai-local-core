"""Pure catalog/surface/host-readiness resolution for admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.services.workspace_product_configuration.contracts import (
    AdmissionConfigurationSource,
)

from .contracts import RootAdmissionRequest


@dataclass(frozen=True)
class ProductResolution:
    product: dict[str, Any] | None
    pcs_id: str | None
    pcs_version: str | None
    product_surface_id: str | None
    configured: bool
    selector_permitted: bool
    host_ready: bool


def _surface(product: dict[str, Any], surface_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in product.get("product_surfaces", [])
            if isinstance(item, dict) and item.get("id") == surface_id
        ),
        None,
    )


def _selector_permitted(
    product: dict[str, Any],
    surface: dict[str, Any],
    request: RootAdmissionRequest,
) -> bool:
    surface_selectors = surface.get("selectors")
    if not isinstance(surface_selectors, dict):
        surface_selectors = {}
    product_selectors = product.get("capability_keys")
    if not isinstance(product_selectors, dict):
        product_selectors = {}
    if request.selector_kind == "api_prefix":
        prefixes = surface_selectors.get("api_prefixes", [])
        return any(
            isinstance(prefix, str)
            and request.selector_key.startswith(prefix)
            for prefix in prefixes
        )
    key = (
        "tool_keys"
        if request.selector_kind == "tool"
        else "playbook_codes"
    )
    scoped = surface_selectors.get(key)
    selectors = scoped if isinstance(scoped, list) else product_selectors.get(key, [])
    return request.selector_key in selectors


def resolve_product(
    source: AdmissionConfigurationSource,
    request: RootAdmissionRequest,
) -> ProductResolution:
    assignments = {
        (item.pcs_id, item.pcs_version): item
        for item in source.snapshot.effective_assignments
    }
    candidates: list[
        tuple[dict[str, Any], tuple[Any, Any], Any, dict[str, Any]]
    ] = []
    configured_surface = None
    for product in source.catalog_products:
        identity = (product.get("pcs_id"), product.get("version"))
        assignment = assignments.get(identity)
        if assignment is None:
            continue
        surfaces = [
            item
            for item in product.get("product_surfaces", [])
            if isinstance(item, dict)
            and (
                request.product_surface_id is None
                or item.get("id") == request.product_surface_id
            )
        ]
        for surface in surfaces:
            configured_surface = (
                configured_surface
                or (product, identity, assignment, surface)
            )
            if _selector_permitted(product, surface, request):
                candidates.append((product, identity, assignment, surface))
    if len(candidates) == 1:
        product, identity, assignment, surface = candidates[0]
        return ProductResolution(
            product=product,
            pcs_id=identity[0],
            pcs_version=identity[1],
            product_surface_id=surface.get("id"),
            configured=True,
            selector_permitted=True,
            host_ready=assignment.host_ready,
        )
    if configured_surface is not None:
        product, identity, assignment, surface = configured_surface
        return ProductResolution(
            product=product,
            pcs_id=identity[0],
            pcs_version=identity[1],
            product_surface_id=surface.get("id"),
            configured=True,
            selector_permitted=False,
            host_ready=assignment.host_ready,
        )
    return ProductResolution(
        product=None,
        pcs_id=None,
        pcs_version=None,
        product_surface_id=request.product_surface_id,
        configured=False,
        selector_permitted=False,
        host_ready=False,
    )

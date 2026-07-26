"""Verify immutable PCS catalog bytes before Local Core materialization."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any

from pydantic import ValidationError

from .contracts import CatalogArtifactEnvelope
from .errors import CatalogArtifactInvalidError


MAX_ARTIFACT_BYTES = 128 * 1024
MAX_PRODUCTS = 64
MAX_PACKS_PER_PRODUCT = 64
HOST_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def verify_catalog_artifact(payload: dict[str, Any]) -> CatalogArtifactEnvelope:
    try:
        artifact = CatalogArtifactEnvelope.model_validate(payload)
    except ValidationError as exc:
        raise CatalogArtifactInvalidError(f"artifact_schema_invalid:{exc}") from exc

    if len(canonical_bytes(payload)) + 1 > MAX_ARTIFACT_BYTES:
        raise CatalogArtifactInvalidError("artifact_size_limit_exceeded")
    actual_catalog_hash = sha256(canonical_bytes(artifact.catalog)).hexdigest()
    if actual_catalog_hash != artifact.catalog_hash:
        raise CatalogArtifactInvalidError("artifact_catalog_hash_mismatch")
    unsigned = {
        key: value
        for key, value in payload.items()
        if key != "artifact_hash"
    }
    actual_artifact_hash = sha256(canonical_bytes(unsigned)).hexdigest()
    if actual_artifact_hash != artifact.artifact_hash:
        raise CatalogArtifactInvalidError("artifact_hash_mismatch")
    _validate_catalog(artifact.catalog)
    return artifact


def _validate_catalog(catalog: dict[str, Any]) -> None:
    products = catalog.get("products")
    if not isinstance(products, list) or not products:
        raise CatalogArtifactInvalidError("artifact_products_missing")
    if len(products) > MAX_PRODUCTS:
        raise CatalogArtifactInvalidError("artifact_product_limit_exceeded")
    identities: set[tuple[str, str]] = set()
    surfaces: set[str] = set()
    for product in products:
        if not isinstance(product, dict):
            raise CatalogArtifactInvalidError("artifact_product_invalid")
        pcs_id = _text(product, "pcs_id")
        version = _text(product, "version")
        identity = (pcs_id, version)
        if identity in identities:
            raise CatalogArtifactInvalidError("artifact_product_duplicate")
        identities.add(identity)
        closure = product.get("pack_closure")
        if not isinstance(closure, list) or not closure:
            raise CatalogArtifactInvalidError(
                f"artifact_product_closure_missing:{pcs_id}"
            )
        if len(closure) > MAX_PACKS_PER_PRODUCT:
            raise CatalogArtifactInvalidError(
                f"artifact_product_closure_limit_exceeded:{pcs_id}"
            )
        for pack in closure:
            _validate_pack_host_requirements(pack, pcs_id=pcs_id)
        product_surfaces = product.get("product_surfaces")
        if not isinstance(product_surfaces, list) or not product_surfaces:
            raise CatalogArtifactInvalidError(
                f"artifact_product_surfaces_missing:{pcs_id}"
            )
        for surface in product_surfaces:
            if not isinstance(surface, dict):
                raise CatalogArtifactInvalidError("artifact_surface_invalid")
            surface_id = _text(surface, "id")
            if surface_id in surfaces:
                raise CatalogArtifactInvalidError(
                    f"artifact_surface_duplicate:{surface_id}"
                )
            surfaces.add(surface_id)


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogArtifactInvalidError(f"artifact_{key}_missing")
    return value.strip()


def _validate_pack_host_requirements(
    pack: Any,
    *,
    pcs_id: str,
) -> None:
    if not isinstance(pack, dict):
        raise CatalogArtifactInvalidError(
            f"artifact_pack_closure_invalid:{pcs_id}"
        )
    requirements = pack.get("host_requirements", [])
    if not isinstance(requirements, list):
        raise CatalogArtifactInvalidError(
            f"artifact_host_requirements_invalid:{pcs_id}"
        )
    seen: set[str] = set()
    for requirement in requirements:
        if (
            not isinstance(requirement, dict)
            or set(requirement) != {"requirement_code", "operations"}
        ):
            raise CatalogArtifactInvalidError(
                f"artifact_host_requirement_invalid:{pcs_id}"
            )
        code = requirement.get("requirement_code")
        operations = requirement.get("operations")
        if (
            not isinstance(code, str)
            or not code
            or code in seen
            or not isinstance(operations, list)
            or not operations
            or any(
                not isinstance(value, str)
                or HOST_OPERATION_RE.fullmatch(value) is None
                for value in operations
            )
            or operations != sorted(set(operations))
        ):
            raise CatalogArtifactInvalidError(
                f"artifact_host_requirement_projection_invalid:{pcs_id}"
            )
        seen.add(code)

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
    KnowledgeProjectionAdapterRegistry,
)
from backend.app.services.capability_registry import load_capabilities


def _manifest(capability_code: str) -> dict:
    return {
        "code": capability_code,
        "version": "1.2.3",
        "object_exports": [
            {
                "kind": "reference",
                "display_name": "Reference",
                "id_field": "id",
            }
        ],
        "knowledge_projections": [
            {
                "id": "reference_retrievable_v1",
                "source_kind": "object",
                "object_kinds": ["reference"],
                "contract_version": "1.0.0",
                "compiler_backend": (
                    f"capabilities.{capability_code}.services.knowledge_projection"
                    ".compiler:compile"
                ),
                "projection_profiles": [
                    "semantic_text",
                    "typed_records",
                    "evidence_graph",
                ],
                "evidence_unit_kinds": ["text_span", "image_region"],
                "derived_text_kinds": ["caption", "vision_summary"],
                "trigger_modes": ["source_revision", "explicit_reindex", "revoke"],
                "graph_profile": {"direct_relations": True},
                "limits": {
                    "max_chunks": 2000,
                    "max_records_per_page": 50000,
                },
            }
        ],
    }


def test_runtime_capability_loader_records_caller_without_crashing(tmp_path: Path):
    load_capabilities(tmp_path, reset=True)


@pytest.mark.parametrize("capability_code", ["synthetic_alpha", "synthetic_beta"])
def test_two_pack_substitution_uses_identical_host_contract(capability_code: str):
    registry = KnowledgeProjectionAdapterRegistry()
    descriptors = registry.register_manifest(
        capability_code,
        _manifest(capability_code),
        Path(f"/runtime/capabilities/{capability_code}"),
    )
    assert len(descriptors) == 1
    descriptor = descriptors[0]

    resolved = registry.resolve(
        capability_code=capability_code,
        capability_version="1.2.3",
        descriptor_id=descriptor.descriptor_id,
        descriptor_hash=descriptor.descriptor_hash,
        manifest_hash=descriptor.manifest_hash,
    )
    portable_shape = resolved.model_dump(
        exclude={"capability_code", "compiler_backend", "manifest_hash", "capability_dir"}
    )
    assert portable_shape["descriptor_id"] == "reference_retrievable_v1"
    assert portable_shape["object_kinds"] == ("reference",)


def test_registry_requires_exact_hash_and_no_prefix_fallback():
    registry = KnowledgeProjectionAdapterRegistry()
    descriptor = registry.register_manifest(
        "synthetic_alpha",
        _manifest("synthetic_alpha"),
        Path("/runtime/capabilities/synthetic_alpha"),
    )[0]

    with pytest.raises(LookupError, match="descriptor_hash_mismatch"):
        registry.resolve(
            capability_code="synthetic_alpha",
            capability_version="1.2.3",
            descriptor_id=descriptor.descriptor_id,
            descriptor_hash="0" * 64,
            manifest_hash=descriptor.manifest_hash,
        )
    with pytest.raises(LookupError, match="not_installed"):
        registry.resolve(
            capability_code="synthetic",
            capability_version="1.2.3",
            descriptor_id=descriptor.descriptor_id,
            descriptor_hash=descriptor.descriptor_hash,
            manifest_hash=descriptor.manifest_hash,
        )


def test_registry_rejects_foreign_backend_and_undeclared_object_kind():
    registry = KnowledgeProjectionAdapterRegistry()
    foreign = _manifest("synthetic_alpha")
    foreign["knowledge_projections"][0]["compiler_backend"] = (
        "capabilities.synthetic_beta.services.compiler:compile"
    )
    with pytest.raises(ValueError, match="backend_must_be_capability_owned"):
        registry.register_manifest(
            "synthetic_alpha",
            foreign,
            Path("/runtime/capabilities/synthetic_alpha"),
        )

    undeclared = _manifest("synthetic_alpha")
    undeclared["knowledge_projections"][0]["object_kinds"] = ["unknown"]
    with pytest.raises(ValueError, match="object_kind_not_exported"):
        registry.register_manifest(
            "synthetic_alpha",
            undeclared,
            Path("/runtime/capabilities/synthetic_alpha"),
        )

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest
import yaml


LOCAL_CORE_ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> dict:
    return {
        "id": "reference_retrievable_v1",
        "source_kind": "object",
        "object_kinds": ["reference"],
        "contract_version": "1.0.0",
        "compiler_backend": (
            "capabilities.synthetic_alpha.services.knowledge_projection.compiler:compile"
        ),
        "projection_profiles": ["semantic_text", "typed_records", "evidence_graph"],
        "evidence_unit_kinds": ["text_span", "image_region"],
        "derived_text_kinds": ["caption"],
        "trigger_modes": ["source_revision", "explicit_reindex", "revoke"],
        "graph_profile": {"direct_relations": True},
        "limits": {"max_chunks": 2000, "max_records_per_page": 50000},
    }


def test_local_manifest_schema_exposes_neutral_knowledge_projection_contract():
    local_schema = yaml.safe_load(
        (LOCAL_CORE_ROOT / "schemas" / "manifest.schema.yaml").read_text()
    )
    projection_schema = local_schema["properties"]["knowledge_projections"]
    assert projection_schema["type"] == "array"
    assert projection_schema["maxItems"] == 32
    assert projection_schema["items"]["additionalProperties"] is False


def test_schema_accepts_neutral_descriptor_and_rejects_security_override():
    schema = yaml.safe_load(
        (LOCAL_CORE_ROOT / "schemas" / "manifest.schema.yaml").read_text()
    )["properties"]["knowledge_projections"]["items"]
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate(_descriptor(), schema)

    invalid = _descriptor()
    invalid["effective_principals"] = ["admin"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_schema_enforces_source_specific_fields_and_host_ceilings():
    schema = yaml.safe_load(
        (LOCAL_CORE_ROOT / "schemas" / "manifest.schema.yaml").read_text()
    )["properties"]["knowledge_projections"]["items"]
    missing_object_kinds = _descriptor()
    missing_object_kinds.pop("object_kinds")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(missing_object_kinds, schema)

    too_large = _descriptor()
    too_large["limits"]["max_chunks"] = 2001
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(too_large, schema)

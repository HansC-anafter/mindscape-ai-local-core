"""Deterministic release-manifest builder for checked-in v1 schemas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_ID = "mindscape.durable-product-semantic-workflow.v1"
OUTCOME_ADAPTER_PORT_ID = "mindscape.product-outcome-adapter-port.v1"
CLOUD_PSC_ID = "psc.cloud.durable-product-semantic-workflow-publication.v1"
LOCAL_CORE_PSC_ID = "psc.local-core.durable-product-semantic-workflow-runtime.v1"
SCHEMA_NAMES = (
    "semantic_execution_identity",
    "workflow_event",
    "checkpoint",
    "approval",
    "side_effect_receipt",
    "replay_envelope",
    "execution_terminal_receipt",
    "outcome_adapter_descriptor",
    "iteration_enrollment",
    "product_iteration",
    "outcome_observation",
    "evaluation_receipt",
    "development_change_attestation",
    "release_health_receipt",
    "evidence_lifecycle_manifest",
    "runtime_owner_decision_receipt",
    "runtime_owner_trusted_keys",
)
MAX_SEGMENT_EVENTS = 10_000
MAX_SEGMENT_CANONICAL_BYTES = 64 * 1024 * 1024


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _schema_path(root: Path, name: str) -> Path:
    return root / "schemas" / f"{name}.schema.json"


def build_release_manifest(root: Path | None = None) -> dict[str, Any]:
    package_root = root or Path(__file__).resolve().parent
    files: dict[str, dict[str, Any]] = {}
    for name in SCHEMA_NAMES:
        path = _schema_path(package_root, name)
        payload = path.read_bytes()
        files[f"schemas/{name}.schema.json"] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    manifest = {
        "contract_id": CONTRACT_ID,
        "contract_version": "1.0.0",
        "outcome_adapter_port_id": OUTCOME_ADAPTER_PORT_ID,
        "cloud_psc_id": CLOUD_PSC_ID,
        "local_core_psc_id": LOCAL_CORE_PSC_ID,
        "source_revision_binding": "development_change_attestation",
        "workflow_kinds": ["execution", "product_iteration", "product_release"],
        "critical_durability": "sync",
        "max_segment_events": MAX_SEGMENT_EVENTS,
        "max_segment_canonical_bytes": MAX_SEGMENT_CANONICAL_BYTES,
        "schemas": files,
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        canonical_json_bytes(manifest)
    ).hexdigest()
    return manifest

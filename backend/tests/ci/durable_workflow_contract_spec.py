from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_ROOT = REPO_ROOT / "scripts" / "ci"
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

from durable_workflow_attestation.models import (  # noqa: E402
    AttestationInputError,
    PROVIDER_ID,
    PROVIDER_IMAGE_DIGEST,
    PROVIDER_SOURCE_COMMIT,
)
from durable_workflow_attestation.trivy_provider import (  # noqa: E402
    validate_provider_metadata,
    validate_scan_receipt,
)
from validate_durable_workflow_contract_parity import validate_parity  # noqa: E402

LOCAL_MIRROR = (
    REPO_ROOT / "backend/app/services/workflow/durable_state/contracts/v1"
)
H = "0" * 64
TREE = "a" * 40
NOW = "2026-07-26T00:00:00Z"


def _provider() -> dict[str, object]:
    return {
        "provider_id": PROVIDER_ID,
        "image_digest": PROVIDER_IMAGE_DIGEST,
        "source_commit": PROVIDER_SOURCE_COMMIT,
        "database_digest": f"sha256:{H}",
        "commands": [
            [
                "trivy",
                "fs",
                "--format",
                "cyclonedx",
                "--output",
                "sbom.json",
                "committed-export",
            ],
            [
                "trivy",
                "fs",
                "--scanners",
                "vuln,license",
                "--format",
                "json",
                "--output",
                "scan.json",
                "committed-export",
            ],
        ],
    }


def _receipt(summary: dict[str, int] | None = None) -> dict[str, object]:
    return {
        "repo_id": "mindscape-ai-cloud",
        "tree_sha": TREE,
        "command_argv": [
            "trivy",
            "fs",
            "--scanners",
            "vuln,license",
            "--format",
            "json",
            "--output",
            "scan.json",
            "committed-export",
        ],
        "scanned_at": NOW,
        "output_sha256": H,
        "output_bytes": 2,
        "finding_summary": summary
        or {
            "critical": 0,
            "high": 0,
            "forbidden": 0,
            "restricted": 0,
            "reciprocal": 0,
            "unknown": 0,
        },
    }


def test_local_manifest_receipts_match_mirrored_schema_bytes() -> None:
    manifest = json.loads((LOCAL_MIRROR / "release_manifest.json").read_text())
    assert len(manifest["schemas"]) == 15
    for relative, receipt in manifest["schemas"].items():
        payload = (LOCAL_MIRROR / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == receipt["sha256"]
        assert len(payload) == receipt["bytes"]


def test_parity_validator_accepts_byte_identical_contract(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    shutil.copytree(LOCAL_MIRROR, canonical)
    assert validate_parity(local_root=LOCAL_MIRROR, canonical_root=canonical) == []


def test_parity_validator_rejects_one_byte_drift(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    local = tmp_path / "local"
    shutil.copytree(LOCAL_MIRROR, canonical)
    shutil.copytree(LOCAL_MIRROR, local)
    schema = local / "schemas/workflow_event.schema.json"
    schema.write_bytes(schema.read_bytes() + b"\n")
    assert "byte parity drift: schemas/workflow_event.schema.json" in validate_parity(
        local_root=local,
        canonical_root=canonical,
    )


def test_exact_trivy_provider_is_required() -> None:
    validate_provider_metadata(_provider())
    wrong = _provider()
    wrong["image_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(AttestationInputError, match="image_digest"):
        validate_provider_metadata(wrong)


def test_mutable_or_expensive_trivy_command_is_rejected() -> None:
    metadata = _provider()
    metadata["commands"][1].insert(-2, "--license-full")
    with pytest.raises(AttestationInputError, match="forbidden"):
        validate_provider_metadata(metadata)


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ({"high": 1}, "blocked"),
        ({"forbidden": 1}, "blocked"),
        ({"unknown": 1}, "needs_human_review"),
        ({}, "admitted"),
    ],
)
def test_trivy_finding_policy(summary: dict[str, int], expected: str) -> None:
    complete = {
        "critical": 0,
        "high": 0,
        "forbidden": 0,
        "restricted": 0,
        "reciprocal": 0,
        "unknown": 0,
    }
    complete.update(summary)
    assert (
        validate_scan_receipt(
            _receipt(complete),
            expected_repo_id="mindscape-ai-cloud",
            expected_tree_sha=TREE,
            kind="scan",
        )
        == expected
    )


def test_scan_receipt_rejects_tree_mismatch() -> None:
    with pytest.raises(AttestationInputError, match="tree SHA mismatch"):
        validate_scan_receipt(
            _receipt(),
            expected_repo_id="mindscape-ai-cloud",
            expected_tree_sha="b" * 40,
            kind="scan",
        )

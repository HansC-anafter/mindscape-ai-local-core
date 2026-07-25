"""One-path composition of a durable workflow attestation draft."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .consumer_impact import validate_hash_receipt
from .git_evidence import collect_repository_evidence
from .models import (
    CONTRACT_ID,
    PROVIDER_ID,
    PROVIDER_IMAGE_DIGEST,
    PROVIDER_SOURCE_COMMIT,
)
from .trivy_provider import validate_provider_metadata, validate_scan_receipt


def _decision(statuses: list[str]) -> str:
    if "blocked" in statuses:
        return "blocked"
    if "needs_human_review" in statuses:
        return "needs_human_review"
    return "admitted"


def build_attestation_draft(
    *,
    cloud_repo: Path,
    local_repo: Path,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    repositories = [
        collect_repository_evidence(
            repo_id="mindscape-ai-cloud",
            repo_path=cloud_repo,
        ),
        collect_repository_evidence(
            repo_id="mindscape-ai-local-core",
            repo_path=local_repo,
        ),
    ]
    provider = dict(evidence.get("provider") or {})
    validate_provider_metadata(provider)
    statuses: list[str] = []
    sbom_receipts: list[dict[str, Any]] = []
    scan_receipts: list[dict[str, Any]] = []
    supplied_sbom = {
        item.get("repo_id"): item for item in evidence.get("sbom_receipts", [])
    }
    supplied_scan = {
        item.get("repo_id"): item
        for item in evidence.get("security_license_receipts", [])
    }
    for repository in repositories:
        sbom = dict(supplied_sbom.get(repository.repo_id) or {})
        scan = dict(supplied_scan.get(repository.repo_id) or {})
        statuses.append(
            validate_scan_receipt(
                sbom,
                expected_repo_id=repository.repo_id,
                expected_tree_sha=repository.tree_sha,
                kind="sbom",
            )
        )
        statuses.append(
            validate_scan_receipt(
                scan,
                expected_repo_id=repository.repo_id,
                expected_tree_sha=repository.tree_sha,
                kind="scan",
            )
        )
        sbom_receipts.append(sbom)
        scan_receipts.append(scan)
    return {
        "attestation_id": str(evidence.get("attestation_id") or ""),
        "contract_id": CONTRACT_ID,
        "repositories": [item.as_dict() for item in repositories],
        "build_artifacts": [
            validate_hash_receipt(item, label="build artifact")
            for item in evidence.get("build_artifacts", [])
        ],
        "configuration_hashes": [
            validate_hash_receipt(item, label="configuration")
            for item in evidence.get("configuration_hashes", [])
        ],
        "data_model_tool_prompt_hashes": [
            validate_hash_receipt(item, label="data/model/tool/prompt")
            for item in evidence.get("data_model_tool_prompt_hashes", [])
        ],
        "dependency_locks": [
            validate_hash_receipt(item, label="dependency lock")
            for item in evidence.get("dependency_locks", [])
        ],
        "sbom_receipts": sbom_receipts,
        "security_license_receipts": scan_receipts,
        "consumer_impact_receipt": validate_hash_receipt(
            dict(evidence.get("consumer_impact_receipt") or {}),
            label="consumer impact",
        ),
        "provider": {
            "provider_id": PROVIDER_ID,
            "image_digest": PROVIDER_IMAGE_DIGEST,
            "source_commit": PROVIDER_SOURCE_COMMIT,
            "database_digest": provider["database_digest"],
            "commands": provider.get("commands") or [],
        },
        "decision": _decision(statuses),
        "exceptions": list(evidence.get("exceptions") or []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "signature": "",
    }

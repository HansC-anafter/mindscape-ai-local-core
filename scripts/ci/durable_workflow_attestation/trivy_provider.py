"""Exact Trivy receipt validation and admission policy."""

from __future__ import annotations

from typing import Any

from .models import (
    AttestationInputError,
    PROVIDER_ID,
    PROVIDER_IMAGE_DIGEST,
    PROVIDER_SOURCE_COMMIT,
    REPO_IDS,
)

SBOM_PREFIX = ("trivy", "fs", "--format", "cyclonedx", "--output")
SCAN_PREFIX = (
    "trivy",
    "fs",
    "--scanners",
    "vuln,license",
    "--format",
    "json",
    "--output",
)
BLOCKING_FINDINGS = ("critical", "high", "forbidden", "restricted")
REVIEW_FINDINGS = ("reciprocal", "unknown")


def _validate_argv(argv: list[str], expected_prefix: tuple[str, ...]) -> None:
    if tuple(argv[: len(expected_prefix)]) != expected_prefix:
        raise AttestationInputError(f"unexpected Trivy command: {argv}")
    if "--license-full" in argv or "latest" in " ".join(argv):
        raise AttestationInputError("mutable or full-license Trivy scan is forbidden")
    if len(argv) != len(expected_prefix) + 2:
        raise AttestationInputError("Trivy command must end with output path and export root")


def validate_provider_metadata(metadata: dict[str, Any]) -> None:
    expected = {
        "provider_id": PROVIDER_ID,
        "image_digest": PROVIDER_IMAGE_DIGEST,
        "source_commit": PROVIDER_SOURCE_COMMIT,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise AttestationInputError(f"Trivy provider mismatch for {key}")
    database_digest = str(metadata.get("database_digest") or "")
    if not database_digest.startswith("sha256:") or len(database_digest) != 71:
        raise AttestationInputError("Trivy database digest is missing or invalid")
    commands = list(metadata.get("commands") or [])
    if len(commands) != 2:
        raise AttestationInputError("exactly one SBOM and one scan command are required")
    _validate_argv(list(commands[0]), SBOM_PREFIX)
    _validate_argv(list(commands[1]), SCAN_PREFIX)


def validate_scan_receipt(
    receipt: dict[str, Any],
    *,
    expected_repo_id: str,
    expected_tree_sha: str,
    kind: str,
) -> str:
    if expected_repo_id not in REPO_IDS or receipt.get("repo_id") != expected_repo_id:
        raise AttestationInputError("scan receipt repository identity mismatch")
    if receipt.get("tree_sha") != expected_tree_sha:
        raise AttestationInputError("scan receipt tree SHA mismatch")
    argv = list(receipt.get("command_argv") or [])
    _validate_argv(argv, SBOM_PREFIX if kind == "sbom" else SCAN_PREFIX)
    output_sha = str(receipt.get("output_sha256") or "")
    if len(output_sha) != 64 or int(receipt.get("output_bytes") or 0) < 2:
        raise AttestationInputError("scan receipt output evidence is incomplete")
    summary = receipt.get("finding_summary")
    if not isinstance(summary, dict):
        raise AttestationInputError("scan finding summary is missing")
    if any(int(summary.get(name, 0)) > 0 for name in BLOCKING_FINDINGS):
        return "blocked"
    if any(int(summary.get(name, 0)) > 0 for name in REVIEW_FINDINGS):
        return "needs_human_review"
    return "admitted"

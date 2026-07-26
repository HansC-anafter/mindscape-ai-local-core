"""Bounded text classification and deterministic redaction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import BinaryIO

from backend.app.core.ports.artifact_disclosure import (
    ArtifactDisclosureFinding,
    DisclosureClassification,
)
from backend.app.services.artifact_disclosure.policy_profile import (
    DisclosurePolicyProfile,
)


_RISK = {
    "public": 0,
    "internal": 1,
    "unknown_binary": 2,
    "confidential": 3,
    "restricted": 4,
}


@dataclass(frozen=True)
class ContentScanResult:
    classification: DisclosureClassification
    findings: tuple[ArtifactDisclosureFinding, ...]
    output_sha256: str
    output_bytes: int
    transformed_content: bytes | None
    external_review_required: bool


def scan_item_content(
    *,
    source_path,
    source_file: BinaryIO | None = None,
    source_sha256: str,
    source_bytes: int,
    media_type: str,
    declared_classification: DisclosureClassification | None,
    profile: DisclosurePolicyProfile,
) -> ContentScanResult:
    if not profile.is_text_media_type(media_type):
        classification = _max_classification(
            "unknown_binary",
            declared_classification,
        )
        return ContentScanResult(
            classification=classification,
            findings=(
                ArtifactDisclosureFinding(
                    code="content_not_text_scanned",
                    count=1,
                ),
            ),
            output_sha256=source_sha256,
            output_bytes=source_bytes,
            transformed_content=None,
            external_review_required=True,
        )
    if source_bytes > profile.max_text_scan_bytes:
        classification = _max_classification(
            "unknown_binary",
            declared_classification,
        )
        return ContentScanResult(
            classification=classification,
            findings=(
                ArtifactDisclosureFinding(
                    code="text_scan_bound_exceeded",
                    count=1,
                ),
            ),
            output_sha256=source_sha256,
            output_bytes=source_bytes,
            transformed_content=None,
            external_review_required=True,
        )
    if source_file is None:
        raw = source_path.read_bytes()
    else:
        source_file.seek(0)
        raw = source_file.read()
        source_file.seek(0)
    if len(raw) != source_bytes:
        raise ValueError("artifact_source_size_drift")
    if hashlib.sha256(raw).hexdigest() != source_sha256:
        raise ValueError("artifact_source_hash_drift")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        classification = _max_classification(
            "unknown_binary",
            declared_classification,
        )
        return ContentScanResult(
            classification=classification,
            findings=(
                ArtifactDisclosureFinding(
                    code="text_decode_failed",
                    count=1,
                ),
            ),
            output_sha256=source_sha256,
            output_bytes=source_bytes,
            transformed_content=None,
            external_review_required=True,
        )

    classification: DisclosureClassification = "internal"
    findings: list[ArtifactDisclosureFinding] = []
    transformed = text
    content_changed = False
    external_review = False
    guard_results: dict[str, bool] = {}
    active_detectors = (
        profile.detectors
        if profile.scan_guard.search(text) is not None
        else ()
    )
    for detector in active_detectors:
        guard_key = detector.prefilter_guard.pattern
        guard_match = guard_results.get(guard_key)
        if guard_match is None:
            guard_match = (
                detector.prefilter_guard.search(text) is not None
            )
            guard_results[guard_key] = guard_match
        if not guard_match:
            continue
        if detector.prefilter.search(text) is None:
            continue
        matches = list(
            detector.pattern.finditer(text)
        )[: profile.max_findings_per_item]
        if not matches:
            continue
        findings.append(
            ArtifactDisclosureFinding(
                code=detector.detector_id,
                count=len(matches),
            )
        )
        classification = _max_classification(
            classification,
            detector.classification,
        )
        external_review = external_review or detector.external_review
        if detector.classification == "confidential":
            transformed = detector.pattern.sub(
                detector.replacement,
                transformed,
            )
            content_changed = True

    classification = _max_classification(
        classification,
        declared_classification,
    )
    transformed_bytes = (
        transformed.encode("utf-8") if content_changed else raw
    )
    return ContentScanResult(
        classification=classification,
        findings=tuple(
            sorted(findings, key=lambda finding: finding.code)
        ),
        output_sha256=(
            hashlib.sha256(transformed_bytes).hexdigest()
            if content_changed
            else source_sha256
        ),
        output_bytes=len(transformed_bytes),
        transformed_content=(
            transformed_bytes if content_changed else None
        ),
        external_review_required=external_review,
    )


def _max_classification(
    left: DisclosureClassification,
    right: DisclosureClassification | None,
) -> DisclosureClassification:
    if right is None:
        return left
    return right if _RISK[right] > _RISK[left] else left


__all__ = ["ContentScanResult", "scan_item_content"]

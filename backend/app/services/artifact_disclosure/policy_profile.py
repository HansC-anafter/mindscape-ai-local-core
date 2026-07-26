"""Strict startup loader for one pinned host disclosure policy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.core.ports.artifact_disclosure import (
    DisclosureAction,
    DisclosureClassification,
    DisclosurePolicyProfileRef,
    DisclosureScope,
)


_CLASSIFICATIONS = {
    "public",
    "internal",
    "confidential",
    "restricted",
    "unknown_binary",
}
_SCOPES = {"workspace", "workspace_group", "external"}
_ACTIONS = {"include", "redact", "block", "review_required"}


@dataclass(frozen=True)
class DetectorRule:
    detector_id: str
    classification: DisclosureClassification
    prefilter_guard: re.Pattern[str]
    prefilter: re.Pattern[str]
    pattern: re.Pattern[str]
    replacement: str
    external_review: bool


@dataclass(frozen=True)
class DisclosurePolicyProfile:
    ref: DisclosurePolicyProfileRef
    max_text_scan_bytes: int
    max_findings_per_item: int
    scan_guard: re.Pattern[str]
    review_acknowledgement: str
    text_media_type_prefixes: tuple[str, ...]
    text_media_types: tuple[str, ...]
    actions: dict[
        DisclosureScope,
        dict[DisclosureClassification, DisclosureAction],
    ]
    detectors: tuple[DetectorRule, ...]

    def action_for(
        self,
        scope: DisclosureScope,
        classification: DisclosureClassification,
    ) -> DisclosureAction:
        return self.actions[scope][classification]

    def is_text_media_type(self, media_type: str) -> bool:
        normalized = media_type.lower().strip()
        return normalized in self.text_media_types or any(
            normalized.startswith(prefix)
            for prefix in self.text_media_type_prefixes
        )


def load_share_policy_profile() -> DisclosurePolicyProfile:
    policy_dir = Path(__file__).resolve().parent / "policies"
    policy_path = policy_dir / "share.v1.json"
    lock_path = policy_dir / "share.v1.sha256"
    raw = policy_path.read_bytes()
    content_sha256 = hashlib.sha256(raw).hexdigest()
    expected_sha256 = lock_path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("disclosure_policy_lock_invalid")
    if content_sha256 != expected_sha256:
        raise ValueError("disclosure_policy_content_hash_mismatch")
    payload = json.loads(raw)
    _validate_profile_payload(payload)
    ref = DisclosurePolicyProfileRef(
        purpose=payload["purpose"],
        version=payload["version"],
        content_sha256=content_sha256,
    )
    actions = {
        scope: {
            classification: action
            for classification, action in payload["actions"][scope].items()
        }
        for scope in sorted(_SCOPES)
    }
    detectors = tuple(
        DetectorRule(
            detector_id=item["id"],
            classification=item["classification"],
            prefilter_guard=re.compile(
                item["prefilter_guard_pattern"]
            ),
            prefilter=re.compile(item["prefilter_pattern"]),
            pattern=re.compile(item["pattern"]),
            replacement=item["replacement"],
            external_review=item["external_review"],
        )
        for item in payload["detectors"]
    )
    return DisclosurePolicyProfile(
        ref=ref,
        max_text_scan_bytes=payload["max_text_scan_bytes"],
        max_findings_per_item=payload["max_findings_per_item"],
        scan_guard=re.compile(payload["scan_guard_pattern"]),
        review_acknowledgement=payload["review_acknowledgement"],
        text_media_type_prefixes=tuple(payload["text_media_type_prefixes"]),
        text_media_types=tuple(payload["text_media_types"]),
        actions=actions,
        detectors=detectors,
    )


def _validate_profile_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise ValueError("disclosure_policy_must_be_object")
    required = {
        "schema_version",
        "purpose",
        "version",
        "max_text_scan_bytes",
        "max_findings_per_item",
        "scan_guard_pattern",
        "review_acknowledgement",
        "text_media_type_prefixes",
        "text_media_types",
        "actions",
        "detectors",
    }
    if set(payload) != required:
        raise ValueError("disclosure_policy_fields_invalid")
    if payload["schema_version"] != "mindscape.artifact-disclosure-policy.v1":
        raise ValueError("disclosure_policy_schema_unsupported")
    if payload["purpose"] != "share" or payload["version"] != "1.0.0":
        raise ValueError("disclosure_policy_identity_invalid")
    if not isinstance(payload["max_text_scan_bytes"], int) or not (
        1 <= payload["max_text_scan_bytes"] <= 128 * 1024 * 1024
    ):
        raise ValueError("disclosure_policy_scan_bound_invalid")
    if not isinstance(payload["max_findings_per_item"], int) or not (
        1 <= payload["max_findings_per_item"] <= 1000
    ):
        raise ValueError("disclosure_policy_finding_bound_invalid")
    if not isinstance(payload["scan_guard_pattern"], str) or not (
        1 <= len(payload["scan_guard_pattern"]) <= 1024
    ):
        raise ValueError("disclosure_policy_scan_guard_invalid")
    try:
        re.compile(payload["scan_guard_pattern"])
    except re.error as exc:
        raise ValueError("disclosure_policy_scan_guard_invalid") from exc
    if not isinstance(payload["review_acknowledgement"], str) or not payload[
        "review_acknowledgement"
    ]:
        raise ValueError("disclosure_policy_review_ack_invalid")
    for key in ("text_media_type_prefixes", "text_media_types"):
        if not isinstance(payload[key], list) or not all(
            isinstance(value, str) and value for value in payload[key]
        ):
            raise ValueError("disclosure_policy_media_types_invalid")
    actions = payload["actions"]
    if not isinstance(actions, dict) or set(actions) != _SCOPES:
        raise ValueError("disclosure_policy_scope_matrix_invalid")
    for matrix in actions.values():
        if not isinstance(matrix, dict) or set(matrix) != _CLASSIFICATIONS:
            raise ValueError("disclosure_policy_action_matrix_invalid")
        if not set(matrix.values()).issubset(_ACTIONS):
            raise ValueError("disclosure_policy_action_invalid")
    detectors = payload["detectors"]
    if not isinstance(detectors, list) or not detectors:
        raise ValueError("disclosure_policy_detectors_required")
    ids: set[str] = set()
    for detector in detectors:
        if not isinstance(detector, dict) or set(detector) != {
            "id",
            "classification",
            "prefilter_guard_pattern",
            "prefilter_pattern",
            "pattern",
            "replacement",
            "external_review",
        }:
            raise ValueError("disclosure_policy_detector_invalid")
        if detector["id"] in ids or not isinstance(detector["id"], str):
            raise ValueError("disclosure_policy_detector_id_invalid")
        ids.add(detector["id"])
        if detector["classification"] not in _CLASSIFICATIONS:
            raise ValueError("disclosure_policy_detector_classification_invalid")
        for pattern_key in (
            "prefilter_guard_pattern",
            "prefilter_pattern",
            "pattern",
        ):
            if not isinstance(detector[pattern_key], str) or not (
                1 <= len(detector[pattern_key]) <= 1024
            ):
                raise ValueError(
                    "disclosure_policy_detector_pattern_invalid"
                )
        if not isinstance(detector["replacement"], str):
            raise ValueError("disclosure_policy_detector_replacement_invalid")
        if not isinstance(detector["external_review"], bool):
            raise ValueError("disclosure_policy_detector_review_invalid")
        try:
            re.compile(detector["prefilter_guard_pattern"])
            re.compile(detector["prefilter_pattern"])
            re.compile(detector["pattern"])
        except re.error as exc:
            raise ValueError("disclosure_policy_detector_regex_invalid") from exc


__all__ = [
    "DetectorRule",
    "DisclosurePolicyProfile",
    "load_share_policy_profile",
]

"""Single in-process implementation of the neutral disclosure port."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from backend.app.core.ports.artifact_disclosure import (
    ArtifactDisclosureDecision,
    ArtifactDisclosureItemDecision,
    ArtifactDisclosurePort,
    ArtifactDisclosureRequest,
    DisclosureAction,
    DisclosurePolicyProfileRef,
)
from backend.app.services.artifact_disclosure.policy_profile import (
    DisclosurePolicyProfile,
)
from backend.app.services.artifact_disclosure.scanner import (
    scan_item_content,
)


class LocalArtifactDisclosureService(ArtifactDisclosurePort):
    """Apply one pinned policy to one bounded request."""

    def __init__(self, profile: DisclosurePolicyProfile) -> None:
        self._profile = profile

    @property
    def policy_ref(self) -> DisclosurePolicyProfileRef:
        return self._profile.ref

    def evaluate(
        self,
        request: ArtifactDisclosureRequest,
    ) -> ArtifactDisclosureDecision:
        if request.policy != self.policy_ref:
            raise ValueError("disclosure_policy_ref_mismatch")
        if not request.items:
            raise ValueError("disclosure_items_required")
        authority = request.authority
        if authority.workspace_id not in authority.allowed_workspace_ids:
            raise ValueError("disclosure_workspace_authority_invalid")

        blocking_codes = self._scope_blocking_codes(request)
        scope_evidence_sha256 = _sha256_json(
            [
                {
                    "item_id": item.item_id,
                    "origin": item.provenance.origin,
                    "source_workspace_id": (
                        item.provenance.source_workspace_id
                    ),
                    "group_id": item.provenance.group_id,
                    "binding_id": item.provenance.binding_id,
                    "resource_id": item.provenance.resource_id,
                    "group_revision": item.provenance.group_revision,
                    "scope_fingerprint": item.provenance.scope_fingerprint,
                }
                for item in request.items
            ]
        )
        scans = []
        for item in request.items:
            scan = scan_item_content(
                source_path=item.source_path,
                source_file=item.analysis_file,
                source_sha256=item.source_sha256,
                source_bytes=item.source_bytes,
                media_type=item.media_type,
                declared_classification=item.declared_classification,
                profile=self._profile,
            )
            if (
                scan.transformed_content is not None
                and item.analysis_file is not None
            ):
                item.analysis_file.seek(0)
                item.analysis_file.truncate()
                item.analysis_file.write(scan.transformed_content)
                item.analysis_file.flush()
                item.analysis_file.seek(0)
                scan = replace(scan, transformed_content=None)
            scans.append(scan)
        baseline = []
        for item, scan in zip(request.items, scans):
            action = self._profile.action_for(
                request.target.scope,
                scan.classification,
            )
            if action == "block":
                blocking_codes.append(
                    f"restricted_content:{item.item_id}"
                )
            baseline.append(
                {
                    "item_id": item.item_id,
                    "classification": scan.classification,
                    "action": action,
                    "source_sha256": item.source_sha256,
                    "output_sha256": scan.output_sha256,
                    "findings": [
                        {"code": finding.code, "count": finding.count}
                        for finding in scan.findings
                    ],
                    "external_review_required": (
                        scan.external_review_required
                    ),
                }
            )
        review_binding_sha256 = _sha256_json(
            {
                "policy": self.policy_ref.__dict__,
                "artifact_set_sha256": request.artifact_set_sha256,
                "target": request.target.__dict__,
                "scope_evidence_sha256": scope_evidence_sha256,
                "items": baseline,
            }
        )
        review_valid = self._review_is_valid(
            request,
            review_binding_sha256,
        )
        review_receipt_sha256 = (
            _sha256_json(
                {
                    "binding_sha256": review_binding_sha256,
                    "acknowledgement": request.review.acknowledgement,
                    "context_sha256": request.authority.context_sha256,
                }
            )
            if review_valid and request.review is not None
            else None
        )
        review_requirements: list[str] = []
        decisions: list[ArtifactDisclosureItemDecision] = []
        for item, scan, base in zip(request.items, scans, baseline):
            action: DisclosureAction = base["action"]
            if (
                request.target.scope == "external"
                and action != "block"
                and not review_valid
            ):
                action = "review_required"
                review_requirements.append(
                    f"verified_owner_review:{item.item_id}"
                )
            decisions.append(
                ArtifactDisclosureItemDecision(
                    item_id=item.item_id,
                    classification=scan.classification,
                    action=action,
                    source_sha256=item.source_sha256,
                    output_sha256=scan.output_sha256,
                    output_bytes=scan.output_bytes,
                    findings=scan.findings,
                    transformed_content=(
                        scan.transformed_content
                        if action == "redact"
                        else None
                    ),
                    transformed_content_file=(
                        item.analysis_file
                        if action == "redact"
                        and scan.output_sha256 != item.source_sha256
                        and item.analysis_file is not None
                        else None
                    ),
                )
            )
        if (
            request.target.scope == "external"
            and request.review is not None
            and not review_valid
        ):
            blocking_codes.append("disclosure_review_invalid")

        blocking = tuple(sorted(set(blocking_codes)))
        requirements = tuple(sorted(set(review_requirements)))
        share_authorization = self._share_authorization(
            scope=request.target.scope,
            blocking=blocking,
            review_requirements=requirements,
            review_valid=review_valid,
        )
        decision_sha256 = _sha256_json(
            {
                "policy": self.policy_ref.__dict__,
                "artifact_set_sha256": request.artifact_set_sha256,
                "target_scope": request.target.scope,
                "scope_evidence_sha256": scope_evidence_sha256,
                "review_binding_sha256": review_binding_sha256,
                "review_receipt_sha256": review_receipt_sha256,
                "share_authorization": share_authorization,
                "blocking_codes": blocking,
                "review_requirements": requirements,
                "items": [
                    {
                        "item_id": item.item_id,
                        "classification": item.classification,
                        "action": item.action,
                        "source_sha256": item.source_sha256,
                        "output_sha256": item.output_sha256,
                        "findings": [
                            {
                                "code": finding.code,
                                "count": finding.count,
                            }
                            for finding in item.findings
                        ],
                    }
                    for item in decisions
                ],
            }
        )
        return ArtifactDisclosureDecision(
            policy=self.policy_ref,
            artifact_set_sha256=request.artifact_set_sha256,
            target_scope=request.target.scope,
            scope_evidence_sha256=scope_evidence_sha256,
            review_binding_sha256=review_binding_sha256,
            review_receipt_sha256=review_receipt_sha256,
            decision_sha256=decision_sha256,
            share_authorization=share_authorization,
            item_decisions=tuple(decisions),
            blocking_codes=blocking,
            review_requirements=requirements,
        )

    def _scope_blocking_codes(
        self,
        request: ArtifactDisclosureRequest,
    ) -> list[str]:
        authority = request.authority
        target = request.target
        codes: list[str] = []
        if target.scope == "external":
            if not target.recipient_ref:
                codes.append("external_recipient_required")
            if authority.actor_user_id != authority.workspace_owner_user_id:
                codes.append("external_workspace_owner_required")
        if target.scope == "workspace_group":
            if authority.active_group_id is None:
                codes.append("workspace_group_context_required")
            elif (
                authority.active_group_id not in authority.allowed_group_ids
                and authority.actor_user_id != authority.group_owner_user_id
            ):
                codes.append("workspace_group_authority_invalid")

        for item in request.items:
            provenance = item.provenance
            if provenance.active_workspace_owner_user_id != (
                authority.workspace_owner_user_id
            ):
                codes.append("active_workspace_owner_evidence_mismatch")
            if provenance.origin == "workspace_owned":
                if provenance.source_workspace_id != authority.workspace_id:
                    codes.append("workspace_provenance_mismatch")
                continue
            required = (
                provenance.group_id,
                provenance.group_owner_user_id,
                provenance.source_workspace_owner_user_id,
                provenance.binding_id,
                provenance.resource_id,
                provenance.group_revision,
                provenance.scope_fingerprint,
            )
            if not all(value is not None for value in required):
                codes.append("workspace_group_provenance_incomplete")
                continue
            if (
                authority.active_group_id is not None
                and provenance.group_id != authority.active_group_id
            ):
                codes.append("workspace_group_provenance_mismatch")
            if target.scope == "external":
                owners = {
                    authority.actor_user_id,
                    authority.workspace_owner_user_id,
                    provenance.active_workspace_owner_user_id,
                    provenance.group_owner_user_id,
                    provenance.source_workspace_owner_user_id,
                }
                if len(owners) != 1:
                    codes.append(
                        "external_multi_owner_consent_unavailable"
                    )
        return codes

    def _review_is_valid(
        self,
        request: ArtifactDisclosureRequest,
        binding_sha256: str,
    ) -> bool:
        if request.target.scope != "external" or request.review is None:
            return False
        return (
            request.review.binding_sha256 == binding_sha256
            and request.review.acknowledgement
            == self._profile.review_acknowledgement
            and request.authority.actor_user_id
            == request.authority.workspace_owner_user_id
        )

    @staticmethod
    def _share_authorization(
        *,
        scope: str,
        blocking: tuple[str, ...],
        review_requirements: tuple[str, ...],
        review_valid: bool,
    ) -> str:
        if blocking:
            return "blocked"
        if scope == "workspace":
            return "workspace_only"
        if scope == "workspace_group":
            return "workspace_group_authorized"
        if review_requirements or not review_valid:
            return "external_review_required"
        return "external_authorized"


def _sha256_json(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["LocalArtifactDisclosureService"]

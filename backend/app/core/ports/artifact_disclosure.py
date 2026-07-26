"""Host-neutral contract for deciding whether artifacts may be disclosed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal, Optional, Protocol


DisclosureScope = Literal["workspace", "workspace_group", "external"]
DisclosureClassification = Literal[
    "public",
    "internal",
    "confidential",
    "restricted",
    "unknown_binary",
]
DisclosureAction = Literal["include", "redact", "block", "review_required"]
ArtifactOrigin = Literal["workspace_owned", "workspace_group_shared"]


@dataclass(frozen=True)
class ArtifactDisclosureAuthority:
    """Verified principal and scope projection supplied by a host controller."""

    workspace_id: str
    actor_user_id: str
    allowed_workspace_ids: tuple[str, ...]
    allowed_group_ids: tuple[str, ...]
    workspace_owner_user_id: str
    active_group_id: Optional[str]
    group_owner_user_id: Optional[str]
    root_execution_id: str
    trace_id: str
    source_entry: str
    context_sha256: str


@dataclass(frozen=True)
class ArtifactProvenanceRef:
    """Authoritative source-scope evidence for one item."""

    origin: ArtifactOrigin
    source_workspace_id: str
    active_workspace_owner_user_id: str
    group_id: Optional[str] = None
    group_owner_user_id: Optional[str] = None
    source_workspace_owner_user_id: Optional[str] = None
    binding_id: Optional[str] = None
    resource_id: Optional[str] = None
    group_revision: Optional[int] = None
    scope_fingerprint: Optional[str] = None


@dataclass(frozen=True)
class ArtifactDisclosureItem:
    """One bounded source item presented to the host policy."""

    item_id: str
    source_ref: str
    source_path: Path
    source_sha256: str
    source_bytes: int
    media_type: str
    provenance: ArtifactProvenanceRef
    declared_classification: Optional[DisclosureClassification] = None
    analysis_file: Optional[BinaryIO] = None


@dataclass(frozen=True)
class ArtifactDisclosureTarget:
    """Requested destination scope; recipient_ref is never identity authority."""

    scope: DisclosureScope
    recipient_ref: Optional[str] = None


@dataclass(frozen=True)
class DisclosurePolicyProfileRef:
    """Pinned policy identity injected by the host composition root."""

    purpose: str
    version: str
    content_sha256: str


@dataclass(frozen=True)
class ArtifactDisclosureReview:
    """User acknowledgement bound to a preflight decision."""

    binding_sha256: str
    acknowledgement: str


@dataclass(frozen=True)
class ArtifactDisclosureFinding:
    """Bounded finding evidence that never contains matched source values."""

    code: str
    count: int


@dataclass(frozen=True)
class ArtifactDisclosureRequest:
    """Complete deterministic input to one policy decision."""

    authority: ArtifactDisclosureAuthority
    artifact_set_sha256: str
    items: tuple[ArtifactDisclosureItem, ...]
    target: ArtifactDisclosureTarget
    policy: DisclosurePolicyProfileRef
    review: Optional[ArtifactDisclosureReview] = None


@dataclass(frozen=True)
class ArtifactDisclosureItemDecision:
    """Action and optional derived bytes for one source item."""

    item_id: str
    classification: DisclosureClassification
    action: DisclosureAction
    source_sha256: str
    output_sha256: str
    output_bytes: int
    findings: tuple[ArtifactDisclosureFinding, ...]
    transformed_content: Optional[bytes] = None
    transformed_content_file: Optional[BinaryIO] = None


@dataclass(frozen=True)
class ArtifactDisclosureDecision:
    """One host decision consumed by an artifact-specific adapter."""

    policy: DisclosurePolicyProfileRef
    artifact_set_sha256: str
    target_scope: DisclosureScope
    scope_evidence_sha256: str
    review_binding_sha256: str
    review_receipt_sha256: Optional[str]
    decision_sha256: str
    share_authorization: str
    item_decisions: tuple[ArtifactDisclosureItemDecision, ...]
    blocking_codes: tuple[str, ...]
    review_requirements: tuple[str, ...]

    @property
    def can_disclose(self) -> bool:
        return not self.blocking_codes and all(
            item.action in {"include", "redact"}
            for item in self.item_decisions
        )


class ArtifactDisclosurePort(Protocol):
    """One synchronous in-process policy boundary."""

    @property
    def policy_ref(self) -> DisclosurePolicyProfileRef:
        ...

    def evaluate(
        self,
        request: ArtifactDisclosureRequest,
    ) -> ArtifactDisclosureDecision:
        ...


__all__ = [
    "ArtifactDisclosureAuthority",
    "ArtifactDisclosureDecision",
    "ArtifactDisclosureFinding",
    "ArtifactDisclosureItem",
    "ArtifactDisclosureItemDecision",
    "ArtifactDisclosurePort",
    "ArtifactDisclosureRequest",
    "ArtifactDisclosureReview",
    "ArtifactDisclosureTarget",
    "ArtifactOrigin",
    "ArtifactProvenanceRef",
    "DisclosureAction",
    "DisclosureClassification",
    "DisclosurePolicyProfileRef",
    "DisclosureScope",
]

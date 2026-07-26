from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.core.ports.artifact_disclosure import (
    ArtifactDisclosureAuthority,
    ArtifactDisclosureItem,
    ArtifactDisclosureRequest,
    ArtifactDisclosureReview,
    ArtifactDisclosureTarget,
    ArtifactProvenanceRef,
)
from backend.app.services.artifact_disclosure.policy_profile import (
    load_share_policy_profile,
)
from backend.app.services.artifact_disclosure.service import (
    LocalArtifactDisclosureService,
)


def _authority(
    *,
    actor: str = "owner-a",
    workspace_owner: str = "owner-a",
    group_owner: str | None = "owner-a",
) -> ArtifactDisclosureAuthority:
    return ArtifactDisclosureAuthority(
        workspace_id="workspace-a",
        actor_user_id=actor,
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=("group-a",),
        workspace_owner_user_id=workspace_owner,
        active_group_id="group-a",
        group_owner_user_id=group_owner,
        root_execution_id="root-a",
        trace_id="trace-a",
        source_entry="local",
        context_sha256="c" * 64,
    )


def _item(
    path: Path,
    *,
    provenance: ArtifactProvenanceRef | None = None,
) -> ArtifactDisclosureItem:
    content = path.read_bytes()
    return ArtifactDisclosureItem(
        item_id="item-a",
        source_ref="item-a",
        source_path=path,
        source_sha256=hashlib.sha256(content).hexdigest(),
        source_bytes=len(content),
        media_type="text/plain",
        provenance=provenance
        or ArtifactProvenanceRef(
            origin="workspace_owned",
            source_workspace_id="workspace-a",
            active_workspace_owner_user_id="owner-a",
        ),
    )


def _request(
    service: LocalArtifactDisclosureService,
    item: ArtifactDisclosureItem,
    *,
    authority: ArtifactDisclosureAuthority | None = None,
    review: ArtifactDisclosureReview | None = None,
) -> ArtifactDisclosureRequest:
    return ArtifactDisclosureRequest(
        authority=authority or _authority(),
        artifact_set_sha256="a" * 64,
        items=(item,),
        target=ArtifactDisclosureTarget(
            scope="external",
            recipient_ref="recipient:reviewed",
        ),
        policy=service.policy_ref,
        review=review,
    )


def test_external_review_is_exact_and_confidential_bytes_are_redacted(
    tmp_path,
):
    path = tmp_path / "evidence.txt"
    path.write_text(
        "Contact person@example.com for the evidence.",
        encoding="utf-8",
    )
    service = LocalArtifactDisclosureService(load_share_policy_profile())
    item = _item(path)

    preflight = service.evaluate(_request(service, item))
    assert preflight.blocking_codes == ()
    assert preflight.share_authorization == "external_review_required"
    assert preflight.item_decisions[0].action == "review_required"
    assert preflight.item_decisions[0].findings[0].code == "email_address"

    approved = service.evaluate(
        _request(
            service,
            item,
            review=ArtifactDisclosureReview(
                binding_sha256=preflight.review_binding_sha256,
                acknowledgement="I_APPROVE_EXTERNAL_DISCLOSURE",
            ),
        )
    )
    assert approved.can_disclose is True
    assert approved.share_authorization == "external_authorized"
    decision = approved.item_decisions[0]
    assert decision.action == "redact"
    assert b"person@example.com" not in decision.transformed_content
    assert b"[REDACTED:EMAIL]" in decision.transformed_content
    assert path.read_text(encoding="utf-8").startswith("Contact person@")


def test_restricted_content_cannot_be_overridden(tmp_path):
    path = tmp_path / "restricted.txt"
    path.write_text(
        "-----BEGIN " + "PRIVATE " + "KEY-----\nsynthetic\n",
        encoding="utf-8",
    )
    service = LocalArtifactDisclosureService(load_share_policy_profile())
    item = _item(path)

    preflight = service.evaluate(_request(service, item))
    assert preflight.share_authorization == "blocked"
    assert preflight.item_decisions[0].action == "block"
    approved = service.evaluate(
        _request(
            service,
            item,
            review=ArtifactDisclosureReview(
                binding_sha256=preflight.review_binding_sha256,
                acknowledgement="I_APPROVE_EXTERNAL_DISCLOSURE",
            ),
        )
    )
    assert approved.can_disclose is False
    assert any(
        code.startswith("restricted_content:")
        for code in approved.blocking_codes
    )


def test_group_external_requires_same_verified_owner(tmp_path):
    path = tmp_path / "shared.txt"
    path.write_text("Internal shared evidence.", encoding="utf-8")
    service = LocalArtifactDisclosureService(load_share_policy_profile())
    provenance = ArtifactProvenanceRef(
        origin="workspace_group_shared",
        source_workspace_id="workspace-source",
        active_workspace_owner_user_id="owner-a",
        group_id="group-a",
        group_owner_user_id="owner-b",
        source_workspace_owner_user_id="owner-c",
        binding_id="binding-a",
        resource_id="resource-a",
        group_revision=1,
        scope_fingerprint="f" * 64,
    )
    decision = service.evaluate(
        _request(
            service,
            _item(path, provenance=provenance),
        )
    )
    assert "external_multi_owner_consent_unavailable" in (
        decision.blocking_codes
    )
    assert decision.can_disclose is False


def test_policy_profile_is_content_hash_pinned():
    profile = load_share_policy_profile()
    assert profile.ref.purpose == "share"
    assert profile.ref.version == "1.0.0"
    assert len(profile.ref.content_sha256) == 64


def test_workspace_must_be_in_verified_allowed_scope_even_for_owner(tmp_path):
    path = tmp_path / "evidence.txt"
    path.write_text("Internal evidence.", encoding="utf-8")
    service = LocalArtifactDisclosureService(load_share_policy_profile())
    authority = ArtifactDisclosureAuthority(
        **{
            **_authority().__dict__,
            "allowed_workspace_ids": (),
        }
    )

    with pytest.raises(
        ValueError,
        match="disclosure_workspace_authority_invalid",
    ):
        service.evaluate(
            _request(
                service,
                _item(path),
                authority=authority,
            )
        )

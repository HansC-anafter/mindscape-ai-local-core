from __future__ import annotations

from backend.app.models.object_runtime import ObjectInstanceRecord, ObjectRef
from backend.app.services.orchestration.meeting.aol_voice_reference_resolver_facade import (
    AolVoiceReferenceResolverFacade,
    MAX_OBJECT_LOOKUP_ROWS,
    normalize_explicit_reference_token,
)


def _record(
    object_id: str,
    *,
    object_kind: str = "asset",
    mention_tokens: list[str] | None = None,
) -> ObjectInstanceRecord:
    return ObjectInstanceRecord(
        ref=ObjectRef(
            uri=f"mindscape://sample/{object_kind}/{object_id}",
            owner_pack="sample",
            object_kind=object_kind,
            object_id=object_id,
            workspace_id="ws_voice",
        ),
        title=f"Object {object_id}",
        mention_tokens=mention_tokens or [],
    )


class _Search:
    def __init__(self, records: list[ObjectInstanceRecord]) -> None:
        self.records = records
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, workspace_id: str, token: str, limit: int):
        self.calls.append((workspace_id, token, limit))
        return self.records


def test_no_explicit_reference_performs_zero_catalog_queries() -> None:
    search = _Search([])
    result = AolVoiceReferenceResolverFacade(object_search=search).resolve(
        transcript="Please recommend a short practice.",
        workspace_id="ws_voice",
        frozen_context_objects=[],
    )

    assert result.status == "not_requested"
    assert result.catalog_query_count == 0
    assert search.calls == []


def test_selected_object_uses_frozen_ref_without_catalog_query() -> None:
    search = _Search([])
    ref = _record("selected-1").ref
    result = AolVoiceReferenceResolverFacade(object_search=search).resolve(
        transcript="Use the selected object for this turn.",
        workspace_id="ws_voice",
        frozen_context_objects=[ref],
    )

    assert result.status == "resolved"
    assert result.explicit_kind == "selected"
    assert result.resolved_references == [ref]
    assert search.calls == []


def test_hash_token_uses_one_bounded_lookup_and_exact_mention_match() -> None:
    search = _Search(
        [
            _record("near", mention_tokens=["#pose-near"]),
            _record("exact", mention_tokens=["#pose-42"]),
        ]
    )
    result = AolVoiceReferenceResolverFacade(object_search=search).resolve(
        transcript="Open #pose-42.",
        workspace_id="ws_voice",
        frozen_context_objects=[],
    )

    assert result.status == "resolved"
    assert result.resolved_references[0].object_id == "exact"
    assert result.catalog_query_count == 1
    assert search.calls == [("ws_voice", "#pose-42", MAX_OBJECT_LOOKUP_ROWS)]


def test_hashtag_and_comment_require_exact_object_kind() -> None:
    hashtag_search = _Search(
        [
            _record("calm", object_kind="asset"),
            _record("calm", object_kind="hashtag"),
        ]
    )
    hashtag = AolVoiceReferenceResolverFacade(
        object_search=hashtag_search
    ).resolve(
        transcript="Use hashtag calm",
        workspace_id="ws_voice",
        frozen_context_objects=[],
    )
    comment_search = _Search(
        [
            _record("c-1", object_kind="asset"),
            _record("c-1", object_kind="comment"),
        ]
    )
    comment = AolVoiceReferenceResolverFacade(
        object_search=comment_search
    ).resolve(
        transcript="Review comment c-1",
        workspace_id="ws_voice",
        frozen_context_objects=[],
    )

    assert hashtag.status == "resolved"
    assert hashtag.resolved_references[0].object_kind == "hashtag"
    assert comment.status == "resolved"
    assert comment.resolved_references[0].object_kind == "comment"


def test_zero_multi_and_multiple_explicit_references_fail_closed() -> None:
    unresolved_search = _Search([_record("other")])
    unresolved = AolVoiceReferenceResolverFacade(
        object_search=unresolved_search
    ).resolve(
        transcript="Use hash missing",
        workspace_id="ws_voice",
        frozen_context_objects=[],
    )
    ambiguous_search = _Search(
        [
            _record("dup", object_kind="comment"),
            ObjectInstanceRecord(
                ref=ObjectRef(
                    uri="mindscape://other/comment/dup",
                    owner_pack="other",
                    object_kind="comment",
                    object_id="dup",
                    workspace_id="ws_voice",
                ),
                title="Other duplicate",
            ),
        ]
    )
    ambiguous = AolVoiceReferenceResolverFacade(
        object_search=ambiguous_search
    ).resolve(
        transcript="Review comment dup",
        workspace_id="ws_voice",
        frozen_context_objects=[],
    )
    multiple_search = _Search([])
    multiple = AolVoiceReferenceResolverFacade(
        object_search=multiple_search
    ).resolve(
        transcript="Use the selected object and hash another",
        workspace_id="ws_voice",
        frozen_context_objects=[_record("selected").ref],
    )

    assert unresolved.status == "unresolved"
    assert ambiguous.status == "ambiguous"
    assert len(ambiguous.candidates) == 2
    assert multiple.status == "count_exceeded"
    assert multiple_search.calls == []


def test_token_normalization_preserves_identity_punctuation() -> None:
    assert normalize_explicit_reference_token("Ａ-1") == "a-1"
    assert normalize_explicit_reference_token("A-1") != (
        normalize_explicit_reference_token("A_1")
    )

"""Exact-only AOL ObjectRef resolution for one final voice transcript."""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

from backend.app.models.object_runtime import ObjectInstanceRecord, ObjectRef
from backend.app.models.workspace_voice_semantic_turn import (
    WorkspaceVoiceReferenceCandidate,
    WorkspaceVoiceReferenceResolution,
)
from backend.app.services.orchestration.meeting.aol_voice_reference_grammar import (
    ExplicitVoiceReference,
    detect_explicit_voice_references,
    normalize_explicit_reference_token,
)
from backend.app.services.stores.object_instance_registry_store import (
    ObjectInstanceRegistryStore,
)


MAX_OBJECT_LOOKUP_ROWS = 8
MAX_REFERENCE_CANDIDATES = 3

ObjectSearch = Callable[[str, str, int], Sequence[ObjectInstanceRecord]]


def _default_search(
    workspace_id: str,
    token: str,
    limit: int,
) -> Sequence[ObjectInstanceRecord]:
    return ObjectInstanceRegistryStore().search(
        workspace_id=workspace_id,
        query=token,
        limit=limit,
    )


def _reference_fields(record: ObjectInstanceRecord) -> Iterable[str]:
    yield record.ref.uri
    yield record.ref.object_id
    yield from record.mention_tokens


def _kind_matches(
    explicit: ExplicitVoiceReference,
    record: ObjectInstanceRecord,
) -> bool:
    if explicit.kind in {"hashtag", "comment"}:
        return record.ref.object_kind == explicit.kind
    return True


def _exact_matches(
    explicit: ExplicitVoiceReference,
    records: Sequence[ObjectInstanceRecord],
) -> list[ObjectInstanceRecord]:
    token = normalize_explicit_reference_token(explicit.token or "")
    matches: list[ObjectInstanceRecord] = []
    seen: set[str] = set()
    for record in records:
        if not _kind_matches(explicit, record):
            continue
        if not any(
            normalize_explicit_reference_token(value) == token
            for value in _reference_fields(record)
        ):
            continue
        if record.ref.uri in seen:
            continue
        seen.add(record.ref.uri)
        matches.append(record)
    return matches


def _candidate(record: ObjectInstanceRecord) -> WorkspaceVoiceReferenceCandidate:
    return WorkspaceVoiceReferenceCandidate(
        object_ref=record.ref,
        display_label=(record.title or record.ref.object_id)[:160],
    )


class AolVoiceReferenceResolverFacade:
    """Resolve one explicit spoken entity without fuzzy auto-selection."""

    def __init__(self, *, object_search: ObjectSearch = _default_search) -> None:
        self._object_search = object_search

    def resolve(
        self,
        *,
        transcript: str,
        workspace_id: str,
        frozen_context_objects: Sequence[ObjectRef],
    ) -> WorkspaceVoiceReferenceResolution:
        explicit_references = detect_explicit_voice_references(transcript)
        if not explicit_references:
            return WorkspaceVoiceReferenceResolution()
        if len(explicit_references) > 1:
            return WorkspaceVoiceReferenceResolution(
                status="count_exceeded",
                reason="reference_count_exceeded",
            )

        explicit = explicit_references[0]
        if explicit.kind == "selected":
            unique = _unique_refs(frozen_context_objects)
            if len(unique) == 1:
                return WorkspaceVoiceReferenceResolution(
                    status="resolved",
                    explicit_kind=explicit.kind,
                    resolved_references=unique,
                )
            status = "unresolved" if not unique else "ambiguous"
            return WorkspaceVoiceReferenceResolution(
                status=status,
                explicit_kind=explicit.kind,
                candidates=[
                    WorkspaceVoiceReferenceCandidate(
                        object_ref=ref,
                        display_label=ref.object_id[:160],
                    )
                    for ref in unique[:MAX_REFERENCE_CANDIDATES]
                ],
                reason=f"selected_reference_{status}",
            )

        records = self._object_search(
            workspace_id,
            explicit.token or "",
            MAX_OBJECT_LOOKUP_ROWS,
        )
        exact = _exact_matches(explicit, records)
        if len(exact) == 1:
            return WorkspaceVoiceReferenceResolution(
                status="resolved",
                explicit_kind=explicit.kind,
                token=explicit.token,
                resolved_references=[exact[0].ref],
                catalog_query_count=1,
            )
        status = "unresolved" if not exact else "ambiguous"
        return WorkspaceVoiceReferenceResolution(
            status=status,
            explicit_kind=explicit.kind,
            token=explicit.token,
            candidates=[
                _candidate(record)
                for record in exact[:MAX_REFERENCE_CANDIDATES]
            ],
            reason=f"{explicit.kind}_reference_{status}",
            catalog_query_count=1,
        )


def _unique_refs(values: Sequence[ObjectRef]) -> list[ObjectRef]:
    unique: list[ObjectRef] = []
    seen: set[str] = set()
    for ref in values:
        if ref.uri in seen:
            continue
        seen.add(ref.uri)
        unique.append(ref)
    return unique


__all__ = [
    "AolVoiceReferenceResolverFacade",
    "MAX_OBJECT_LOOKUP_ROWS",
    "MAX_REFERENCE_CANDIDATES",
    "normalize_explicit_reference_token",
]

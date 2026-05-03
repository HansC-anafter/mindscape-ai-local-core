"""Server-side normalization for Meeting Workbench command envelopes."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingRequestedAction,
)
from backend.app.models.object_runtime import ObjectRef, ObjectRoleEntry, SelectionResolveError


OBJECT_MENTION_RE = re.compile(
    r"@(?P<owner>[A-Za-z0-9_-]+)\.(?P<kind>[A-Za-z0-9_-]+):(?P<object_id>[^\s,;]+)"
)
RAW_MENTION_RE = re.compile(r"@[\w./:-]+")
SLASH_VERB_RE = re.compile(r"^\s*/(?P<verb>[A-Za-z][A-Za-z0-9_-]*)\b")
ROLE_HINT_RE = re.compile(
    r"^(?:\s+(?:as|for)\s+(?P<role>source|target|baseline|constraint|evidence|character|output|meeting|session|node)\b)",
    re.IGNORECASE,
)

DEFAULT_ROLE_BY_VERB = {
    "stage": "target",
    "review": "target",
    "promote": "target",
    "attach": "source",
    "recommend": "source",
    "expand": "source",
    "preview": "source",
}


class MeetingCommandParseResult(BaseModel):
    """Normalized command grammar extracted from intent text."""

    normalized_intent_text: str
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    requested_action: Optional[MeetingRequestedAction] = None
    unresolved_mentions: List[str] = Field(default_factory=list)
    errors: List[SelectionResolveError] = Field(default_factory=list)


class MeetingCommandNormalizationError(ValueError):
    """Raised when server-side command normalization finds invalid refs."""

    def __init__(self, errors: List[SelectionResolveError]):
        super().__init__("invalid meeting command envelope")
        self.errors = errors


def _role_after_match(intent_text: str, end_index: int, verb: Optional[str]) -> str:
    tail = intent_text[end_index : end_index + 48]
    role_match = ROLE_HINT_RE.match(tail)
    if role_match:
        return role_match.group("role").lower()
    prefix = intent_text[max(0, end_index - 96) : end_index].lower()
    if prefix.rstrip().endswith(" for"):
        return "target"
    return DEFAULT_ROLE_BY_VERB.get((verb or "").lower(), "source")


def _object_ref_from_match(match: re.Match[str], workspace_id: str) -> ObjectRef:
    owner_pack = match.group("owner")
    object_kind = match.group("kind")
    object_id = match.group("object_id").rstrip(".,)")
    return ObjectRef(
        uri=f"mindscape://{owner_pack}/{object_kind}/{object_id}",
        owner_pack=owner_pack,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id=workspace_id,
    )


def parse_meeting_command_text(
    intent_text: str,
    *,
    workspace_id: str,
) -> MeetingCommandParseResult:
    """Parse the intentionally small P0 command grammar.

    Supported grammar:
    - free text
    - leading slash verb, for example `/stage`
    - object mentions in `@owner.kind:id` form
    - local role hints, for example `as source` or `for target`
    """

    normalized = " ".join(str(intent_text or "").split())
    slash_match = SLASH_VERB_RE.match(normalized)
    verb = slash_match.group("verb").lower() if slash_match else None
    requested_action = MeetingRequestedAction(verb=verb) if verb else None

    entries: List[ObjectRoleEntry] = []
    parsed_tokens: set[str] = set()
    seen_uris: set[str] = set()
    for match in OBJECT_MENTION_RE.finditer(normalized):
        token = match.group(0).rstrip(".,)")
        parsed_tokens.add(token)
        ref = _object_ref_from_match(match, workspace_id)
        if ref.uri in seen_uris:
            continue
        seen_uris.add(ref.uri)
        entries.append(
            ObjectRoleEntry(
                role=_role_after_match(normalized, match.end(), verb),
                ref=ref,
            )
        )

    unresolved = []
    errors: List[SelectionResolveError] = []
    for raw_match in RAW_MENTION_RE.finditer(normalized):
        token = raw_match.group(0).rstrip(".,)")
        if token in parsed_tokens:
            continue
        unresolved.append(token)
        errors.append(
            SelectionResolveError(
                code="invalid_command_reference",
                message=f"Unsupported meeting command mention '{token}'. Use @owner.kind:id.",
            )
        )

    return MeetingCommandParseResult(
        normalized_intent_text=normalized,
        context_objects=entries,
        requested_action=requested_action,
        unresolved_mentions=unresolved,
        errors=errors,
    )


def _entry_key(entry: ObjectRoleEntry) -> tuple[str, str]:
    return entry.role, entry.ref.uri


def canonicalize_meeting_command_envelope(
    envelope: MeetingCommandEnvelope,
    *,
    workspace_id: str,
    meeting_id: str,
) -> MeetingCommandEnvelope:
    """Return a server-canonical envelope or raise no exceptions.

    Validation that needs HTTP status mapping remains in the route; this helper only
    normalizes intent text and merges server-parsed role-bearing refs.
    """

    parsed = parse_meeting_command_text(envelope.intent_text, workspace_id=workspace_id)
    merged_entries: List[ObjectRoleEntry] = []
    seen: set[tuple[str, str]] = set()
    for entry in [*envelope.context_objects, *parsed.context_objects]:
        key = _entry_key(entry)
        if key in seen:
            continue
        seen.add(key)
        ref_workspace_id = entry.ref.workspace_id
        if ref_workspace_id and ref_workspace_id != workspace_id:
            parsed.errors.append(
                SelectionResolveError(
                    code="cross_workspace_command_reference",
                    message=(
                        f"Object reference '{entry.ref.uri}' belongs to workspace "
                        f"'{ref_workspace_id}', not '{workspace_id}'."
                    ),
                )
            )
        merged_entries.append(entry)

    if parsed.errors:
        raise MeetingCommandNormalizationError(parsed.errors)

    metadata: Dict[str, object] = dict(envelope.metadata)
    if parsed.unresolved_mentions:
        metadata["unresolved_mentions"] = parsed.unresolved_mentions

    requested_action = envelope.requested_action or parsed.requested_action
    if requested_action is None and envelope.write_mode:
        requested_action = MeetingRequestedAction(write_mode=envelope.write_mode)
    elif requested_action is not None and requested_action.write_mode is None:
        requested_action = requested_action.model_copy(
            update={"write_mode": envelope.write_mode}
        )

    return envelope.model_copy(
        update={
            "workspace_id": workspace_id,
            "meeting_id": meeting_id,
            "intent_text": parsed.normalized_intent_text,
            "context_objects": merged_entries,
            "requested_action": requested_action,
            "metadata": metadata,
        }
    )

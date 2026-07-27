"""Pure explicit-reference grammar for final Workspace voice transcripts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.app.models.workspace_voice_semantic_turn import (
    WorkspaceVoiceExplicitReferenceKind,
)


_SELECTED_PATTERNS = (
    re.compile(
        r"(?<!\w)(?:the\s+)?(?:currently\s+)?selected\s+object(?!\w)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:目前|當前|当前)?(?:選取|选取|選中|选中)的?(?:物件|对象|物體|物体)"),
    re.compile(r"(?:這個|这个|那個|那个)(?:物件|对象|物體|物体)"),
)
_TOKEN_PATTERNS: tuple[
    tuple[WorkspaceVoiceExplicitReferenceKind, re.Pattern[str]],
    ...,
] = (
    ("comment", re.compile(r"(?<!\w)comment\s+([^\s,;!?，；！？]+)", re.IGNORECASE)),
    ("comment", re.compile(r"(?:留言|評論|评论)\s*([^\s,;!?，；！？]+)")),
    ("hashtag", re.compile(r"(?<!\w)hashtag\s+([^\s,;!?，；！？]+)", re.IGNORECASE)),
    ("hashtag", re.compile(r"(?:話題標籤|话题标签)\s*([^\s,;!?，；！？]+)")),
    ("hash", re.compile(r"(?<!\w)hash\s+([^\s,;!?，；！？]+)", re.IGNORECASE)),
    ("hash", re.compile(r"(?:雜湊|哈希|井號)\s*([^\s,;!?，；！？]+)")),
    ("hash", re.compile(r"(?<!\w)(#[^\s,;!?，；！？]+)")),
)


@dataclass(frozen=True)
class ExplicitVoiceReference:
    kind: WorkspaceVoiceExplicitReferenceKind
    token: str | None


def normalize_explicit_reference_token(value: str) -> str:
    """Normalize identity text without deleting meaningful punctuation."""

    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def detect_explicit_voice_references(
    transcript: str,
) -> list[ExplicitVoiceReference]:
    """Return references in spoken order; the resolver enforces the count cap."""

    matches: list[tuple[int, ExplicitVoiceReference]] = []
    for pattern in _SELECTED_PATTERNS:
        for match in pattern.finditer(transcript):
            matches.append((match.start(), ExplicitVoiceReference("selected", None)))
    for kind, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(transcript):
            token = str(match.group(1) or "").strip().rstrip(".。")
            if token:
                matches.append((match.start(), ExplicitVoiceReference(kind, token)))
    return [reference for _, reference in sorted(matches, key=lambda item: item[0])]


__all__ = [
    "ExplicitVoiceReference",
    "detect_explicit_voice_references",
    "normalize_explicit_reference_token",
]

"""Enum types used by workspace runtime profiles."""

from enum import Enum


class RationaleLevel(str, Enum):
    """Output rationale level."""

    NONE = "none"
    BRIEF = "brief"
    DETAILED = "detailed"


class CodingStyle(str, Enum):
    """Coding output style."""

    PATCH_FIRST = "patch_first"
    EXPLAIN_FIRST = "explain_first"
    CODE_ONLY = "code_only"


class WritingStyle(str, Enum):
    """Writing output style."""

    STRUCTURE_FIRST = "structure_first"
    DRAFT_FIRST = "draft_first"
    BOTH = "both"


class ConfirmationFormat(str, Enum):
    """Confirmation format."""

    LIST_CHANGES = "list_changes"
    SUMMARY = "summary"
    DETAILED = "detailed"

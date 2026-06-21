"""Memory contract enum and time helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryLayer(str, Enum):
    PROCESS = "process"
    EPISODIC = "episodic"
    INTERFACE = "interface"
    CORE = "core"
    PROCEDURAL = "procedural"


class MemoryKind(str, Enum):
    SESSION_EPISODE = "session_episode"
    DECISION_EPISODE = "decision_episode"
    PATTERN_CANDIDATE = "pattern_candidate"
    CONTEXT_SIGNATURE = "context_signature"
    PREFERENCE = "preference"
    PRINCIPLE = "principle"
    PROCEDURAL_RULE = "procedural_rule"


class MemoryVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    OBSERVED = "observed"
    VERIFIED = "verified"
    CHALLENGED = "challenged"
    REJECTED = "rejected"


class MemoryLifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class MemoryUpdateMode(str, Enum):
    APPEND = "append"
    REVISE = "revise"
    SUPERSEDE = "supersede"
    INVALIDATE = "invalidate"
    MERGE = "merge"


class MemoryEdgeType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    CONTINUES = "continues"
    SUPERSEDES = "supersedes"


class MemoryWritebackRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

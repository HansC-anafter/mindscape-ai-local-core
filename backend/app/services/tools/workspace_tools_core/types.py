"""Shared types for workspace tool helpers."""

from __future__ import annotations

from typing import Any, Dict, TypeAlias

ExecutionCandidate: TypeAlias = Dict[str, Any]
TableReference: TypeAlias = tuple[str, str]

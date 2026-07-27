"""Stable result contracts for the authorization-aware knowledge writer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AuthorizedIndexWriteResult:
    state: str
    indexed_chunks: int
    revision_id: str
    embedding_model: Optional[str]
    knowledge_resource_id: str
    security_label_id: str
    projection_revision_id: str
    authz_revision: int


@dataclass(frozen=True)
class AuthorizedIndexRevokeResult:
    state: str
    knowledge_resource_id: str
    security_label_id: str
    projection_revision_id: Optional[str]
    authz_revision: Optional[int]


__all__ = ["AuthorizedIndexRevokeResult", "AuthorizedIndexWriteResult"]

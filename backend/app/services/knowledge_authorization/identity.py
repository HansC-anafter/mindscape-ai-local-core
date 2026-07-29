"""Frozen deterministic identities shared by ACL migrations and writers."""

from __future__ import annotations

import hashlib
from typing import Iterable


_SEPARATOR = "\x1f"


def _stable_id(prefix: str, parts: Iterable[str]) -> str:
    normalized = tuple(str(part).strip() for part in parts)
    if any(not part for part in normalized):
        raise ValueError(f"{prefix}_identity_part_required")
    digest = hashlib.sha256(_SEPARATOR.join(normalized).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def knowledge_resource_id(
    *,
    owner_capability_code: str,
    source_kind: str,
    source_ref: str,
    owner_scope_type: str,
    owner_scope_id: str,
) -> str:
    return _stable_id(
        "kr",
        (
            owner_capability_code,
            source_kind,
            source_ref,
            owner_scope_type,
            owner_scope_id,
        ),
    )


def security_label_id(resource_id: str) -> str:
    return _stable_id("ksl", (resource_id,))


def security_grant_id(
    *,
    label_id: str,
    principal_type: str,
    principal_id: str,
    relation: str,
    effect: str,
) -> str:
    return _stable_id(
        "kg",
        (label_id, principal_type, principal_id, relation, effect),
    )


def acl_mutation_id(
    *,
    resource_id: str,
    authz_revision: int,
    diff_digest: str,
) -> str:
    return _stable_id(
        "kam",
        (resource_id, str(authz_revision), diff_digest),
    )


__all__ = [
    "acl_mutation_id",
    "knowledge_resource_id",
    "security_grant_id",
    "security_label_id",
]

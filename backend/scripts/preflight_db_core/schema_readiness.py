"""Role-specific public schema readiness policy for backend startup."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


BASE_REQUIRED_RELATIONS = (
    "profiles",
    "workspaces",
    "system_settings",
    "user_configs",
)

EXECUTION_ADMISSION_RELATIONS = (
    "host_runtime_bindings",
    "host_runtime_attestations",
    "workspace_host_grants",
    "host_runtime_receipts",
)

_EXECUTION_BACKEND_ROLES = frozenset({"execution", "stable"})


def required_relations_for_backend_role(role: str) -> tuple[str, ...]:
    """Return the immutable startup relation contract for one backend role."""

    normalized_role = str(role or "").strip().lower()
    if normalized_role in _EXECUTION_BACKEND_ROLES:
        return BASE_REQUIRED_RELATIONS + EXECUTION_ADMISSION_RELATIONS
    return BASE_REQUIRED_RELATIONS


def find_missing_public_relations(
    cursor: Any,
    relations: Sequence[str],
) -> tuple[str, ...]:
    """Check an ordered relation set with one parameterized catalog statement."""

    normalized_relations = tuple(
        dict.fromkeys(
            relation_name
            for raw_name in relations
            if (relation_name := str(raw_name).strip())
        )
    )
    if not normalized_relations:
        return ()

    cursor.execute(
        "SELECT required.relation_name "
        "FROM unnest(%s::text[]) WITH ORDINALITY "
        "  AS required(relation_name, position) "
        "WHERE to_regclass(format('%%I.%%I', 'public', required.relation_name)) IS NULL "
        "ORDER BY required.position",
        (list(normalized_relations),),
    )
    return tuple(str(row[0]) for row in cursor.fetchall())


__all__ = [
    "BASE_REQUIRED_RELATIONS",
    "EXECUTION_ADMISSION_RELATIONS",
    "find_missing_public_relations",
    "required_relations_for_backend_role",
]

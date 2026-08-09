"""Fail-closed runtime migration catalog integrity seam."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


RevisionSetResolver = Callable[[str], set[str]]
AppliedRevisionResolver = Callable[[str, set[str]], set[str]]


def resolve_runtime_catalog_snapshot(
    *,
    db_type: str,
    current_revisions: set[str],
    runtime_known_revisions_resolver: RevisionSetResolver,
    applied_revisions_resolver: AppliedRevisionResolver,
) -> dict[str, Any]:
    """Resolve the live migration DAG or return a fail-closed diagnostic."""

    runtime_known_revisions = runtime_known_revisions_resolver(db_type)
    if not runtime_known_revisions:
        return {
            "status": "error",
            "error": f"Could not enumerate the {db_type} runtime migration catalog.",
            "catalog_complete": False,
            "current_revisions": sorted(current_revisions),
            "unresolved_current_heads": sorted(current_revisions),
        }

    unresolved_current_heads = sorted(
        current_revisions - runtime_known_revisions
    )
    if unresolved_current_heads:
        return {
            "status": "error",
            "error": (
                f"The {db_type} runtime migration catalog cannot resolve "
                f"live heads: {', '.join(unresolved_current_heads)}"
            ),
            "catalog_complete": False,
            "current_revisions": sorted(current_revisions),
            "unresolved_current_heads": unresolved_current_heads,
        }

    applied_revisions = applied_revisions_resolver(
        db_type,
        current_revisions,
    )
    return {
        "status": "success",
        "catalog_complete": True,
        "current_revisions": sorted(current_revisions),
        "unresolved_current_heads": [],
        "runtime_known_revisions": sorted(runtime_known_revisions),
        "applied_revisions": sorted(applied_revisions),
    }


__all__ = ["resolve_runtime_catalog_snapshot"]

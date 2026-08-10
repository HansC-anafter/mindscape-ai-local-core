"""Adapter for host-resource schema contract checks used by migration orchestration."""

from __future__ import annotations

from typing import Dict

from app.services.host_resources.schema_readiness import (
    REQUIRED_REVISION as HOST_RESOURCE_REQUIRED_REVISION,
    check_host_resource_schema_readiness,
)


def evaluate_host_resource_schema_contract(
    *,
    db_type: str,
    applied_revisions: set[str],
) -> Dict | None:
    """Return schema-drift diagnostic when host-resource contract is incomplete."""

    if db_type != "postgres":
        return None
    if HOST_RESOURCE_REQUIRED_REVISION not in applied_revisions:
        return None

    host_resource_schema = check_host_resource_schema_readiness()
    if host_resource_schema.get("error"):
        return {
            "status": "schema_drift",
            "error": (
                "Could not verify host-resource schema readiness. "
                "Migration is required before continuing."
            ),
            "host_resource_schema": host_resource_schema,
        }

    if not host_resource_schema.get("ready", False):
        return {
            "status": "schema_drift",
            "error": (
                "Host-resource ledger schema is partially applied. "
                f"Revision {HOST_RESOURCE_REQUIRED_REVISION} is in "
                "alembic_version, but required host-resource schema objects "
                "are missing."
            ),
            "host_resource_schema": host_resource_schema,
        }

    return None

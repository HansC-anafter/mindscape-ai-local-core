"""Version upgrades for persisted composition graph drafts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

COMPOSITION_GRAPH_SCHEMA_VERSION = "composition_graph.v1"


def upgrade_composition_graph_content(content: Dict[str, Any]) -> Dict[str, Any]:
    current_version = str(content.get("schema_version") or COMPOSITION_GRAPH_SCHEMA_VERSION)
    if current_version == COMPOSITION_GRAPH_SCHEMA_VERSION:
        return content

    migrations = list(content.get("migrations") or [])
    migrations.append(
        {
            "from_version": current_version,
            "to_version": COMPOSITION_GRAPH_SCHEMA_VERSION,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {
        **content,
        "schema_version": COMPOSITION_GRAPH_SCHEMA_VERSION,
        "migrations": migrations,
    }

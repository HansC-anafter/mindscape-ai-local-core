from __future__ import annotations

from typing import Any, Dict, List

from ..schema.world_state_snapshot import WorldStateSnapshot


class SpatialQueryService:
    """Build bounded query surfaces from a governed snapshot."""

    def build_visibility_index(self, snapshot: WorldStateSnapshot) -> List[str]:
        return list(snapshot.visible_objects)

    def build_reachability_index(self, snapshot: WorldStateSnapshot) -> List[str]:
        return list(snapshot.reachable_zones)

    def build_resource_constraints(self, snapshot: WorldStateSnapshot) -> Dict[str, Any]:
        return dict(snapshot.resource_constraints)

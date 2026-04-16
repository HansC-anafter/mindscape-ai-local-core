from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from ..schema.world_memory_delta import WorldMemoryDelta
from ..schema.world_memory_packet import WorldMemoryPacket
from ..schema.world_memory_root import WorldMemoryRoot
from ..schema.world_state_snapshot import WorldStateSnapshot
from .spatial_query_service import SpatialQueryService


def _normalize_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item or "").strip()]
    if value in (None, ""):
        return []
    return [str(value)]


def _normalize_motion_artifact_refs(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if isinstance(item, dict) and item:
            normalized.append(dict(item))
    return normalized


def _derive_active_motion(motion_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    active_motion = motion_context.get("active_motion")
    if isinstance(active_motion, dict) and active_motion:
        return dict(active_motion)

    fallback = {
        key: motion_context.get(key)
        for key in (
            "motion_id",
            "provider",
            "source_family",
            "status",
            "duration_sec",
            "fps",
            "skeleton_family",
            "skeleton_version",
            "coordinate_space",
            "retarget_profile",
        )
        if motion_context.get(key) is not None
    }
    return fallback or None


def _derive_motion_constraints(motion_context: Dict[str, Any]) -> Dict[str, Any]:
    explicit = motion_context.get("motion_constraints")
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)

    constraints: Dict[str, Any] = {}
    timing_policy = motion_context.get("timing_policy")
    if isinstance(timing_policy, dict) and timing_policy:
        constraints["timing_policy"] = dict(timing_policy)
    retarget_profile = motion_context.get("retarget_profile")
    if retarget_profile:
        constraints["retarget_profile"] = retarget_profile
    return constraints


def _normalize_schedule_artifact_refs(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if isinstance(item, dict) and item:
            normalized.append(dict(item))
    return normalized


def _derive_active_schedule(
    spatial_schedule_context: Dict[str, Any],
    source_receipt: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    explicit = spatial_schedule_context.get("active_schedule")
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)

    fallback = {
        key: spatial_schedule_context.get(key)
        for key in (
            "schedule_id",
            "status",
            "title",
            "entity_kinds",
            "active_segment_ids",
            "segment_count",
            "time_window",
            "consumer_refs",
            "source_task_id",
            "source_session_id",
            "source_artifact_id",
            "updated_at",
        )
        if spatial_schedule_context.get(key) not in (None, "", [], {})
    }
    if fallback:
        return fallback

    packet_schedule = source_receipt.get("active_schedule")
    if isinstance(packet_schedule, dict) and packet_schedule:
        return dict(packet_schedule)
    return None


def _derive_schedule_constraints(
    spatial_schedule_context: Dict[str, Any],
    source_receipt: Dict[str, Any],
) -> Dict[str, Any]:
    explicit = spatial_schedule_context.get("schedule_constraints")
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)

    summary = spatial_schedule_context.get("constraint_summary")
    if isinstance(summary, dict) and summary:
        return dict(summary)

    packet_constraints = source_receipt.get("schedule_constraints")
    if isinstance(packet_constraints, dict) and packet_constraints:
        return dict(packet_constraints)
    return {}


def _derive_schedule_artifact_refs(
    spatial_schedule_context: Dict[str, Any],
    source_receipt: Dict[str, Any],
) -> List[Dict[str, Any]]:
    refs = _normalize_schedule_artifact_refs(spatial_schedule_context.get("artifact_refs"))
    if refs:
        return refs
    return _normalize_schedule_artifact_refs(source_receipt.get("schedule_artifact_refs"))


class WorldStateAdapter:
    """Normalize coarse receipts into governed world-state models."""

    def __init__(self, query_service: Optional[SpatialQueryService] = None):
        self.query_service = query_service or SpatialQueryService()

    def normalize_receipt(
        self,
        *,
        workspace_id: str,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        governance_context: Optional[Dict[str, Any]] = None,
        receipt: Optional[Dict[str, Any]] = None,
        geo_context: Optional[Dict[str, Any]] = None,
        motion_context: Optional[Dict[str, Any]] = None,
        spatial_schedule_context: Optional[Dict[str, Any]] = None,
    ) -> WorldStateSnapshot:
        source_receipt = dict(receipt or {})
        geo_context = dict(geo_context or {})
        motion_context = dict(motion_context or {})
        spatial_schedule_context = dict(spatial_schedule_context or {})
        governance_context = dict(governance_context or {})
        lens_context = dict(governance_context.get("lens") or {})
        mode = governance_context.get("mode")
        execution_mode = governance_context.get("execution_mode")

        scene_id = source_receipt.get("scene_id") or lens_context.get("lens_id") or f"workspace:{workspace_id}"
        current_zone = source_receipt.get("current_zone") or (
            "governed_workspace" if mode else None
        )

        environment_state = dict(source_receipt.get("environment_state") or {})
        if mode:
            environment_state.setdefault("workspace_mode", mode)
        if execution_mode:
            environment_state.setdefault("execution_mode", execution_mode)

        performer_state = dict(source_receipt.get("performer_state") or {})
        if profile_id:
            performer_state.setdefault("profile_id", profile_id)

        resource_constraints = dict(source_receipt.get("resource_constraints") or {})
        resource_constraints.setdefault("world_source", source_receipt.get("source", "synthetic"))

        return WorldStateSnapshot(
            snapshot_id=str(source_receipt.get("snapshot_id") or uuid4()),
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            source=str(source_receipt.get("source") or "synthetic"),
            scene_id=str(scene_id),
            current_zone=current_zone,
            visible_objects=_normalize_list(source_receipt.get("visible_objects")),
            reachable_zones=_normalize_list(source_receipt.get("reachable_zones")),
            resource_constraints=resource_constraints,
            environment_state=environment_state,
            performer_state=performer_state,
            active_motion=_derive_active_motion(motion_context),
            motion_artifact_refs=_normalize_motion_artifact_refs(
                motion_context.get("artifact_refs")
            ),
            motion_constraints=_derive_motion_constraints(motion_context),
            active_schedule=_derive_active_schedule(
                spatial_schedule_context,
                source_receipt,
            ),
            schedule_artifact_refs=_derive_schedule_artifact_refs(
                spatial_schedule_context,
                source_receipt,
            ),
            schedule_constraints=_derive_schedule_constraints(
                spatial_schedule_context,
                source_receipt,
            ),
            geo_anchor=source_receipt.get("geo_anchor") or geo_context.get("geo_anchor"),
            venue_context=source_receipt.get("venue_context") or geo_context.get("venue_context"),
            route_context=source_receipt.get("route_context") or geo_context.get("route_context"),
            streetview_context=source_receipt.get("streetview_context") or geo_context.get("streetview_context"),
            metadata={
                **dict(source_receipt.get("metadata") or {}),
                "geo_provider": geo_context.get("provider"),
                "motion_provider": motion_context.get("provider"),
                "has_spatial_schedule": bool(spatial_schedule_context),
            },
        )

    def build_root(self, snapshot: WorldStateSnapshot) -> WorldMemoryRoot:
        return WorldMemoryRoot(
            workspace_id=snapshot.workspace_id,
            current_snapshot=snapshot,
            history_snapshot_ids=[snapshot.snapshot_id],
            source_receipt_types=[snapshot.source],
            active_geo_anchor=snapshot.geo_anchor,
            metadata=dict(snapshot.metadata),
        )

    def build_delta(
        self,
        snapshot: WorldStateSnapshot,
        *,
        changed_fields: Optional[Iterable[str]] = None,
    ) -> WorldMemoryDelta:
        return WorldMemoryDelta(
            workspace_id=snapshot.workspace_id,
            snapshot_id=snapshot.snapshot_id,
            changed_fields=list(changed_fields or []),
            metadata={"source": snapshot.source},
        )

    def build_packet(self, snapshot: WorldStateSnapshot) -> WorldMemoryPacket:
        return WorldMemoryPacket(
            workspace_id=snapshot.workspace_id,
            snapshot_id=snapshot.snapshot_id,
            source=snapshot.source,
            scene_id=snapshot.scene_id,
            current_zone=snapshot.current_zone,
            visible_objects=self.query_service.build_visibility_index(snapshot),
            reachable_zones=self.query_service.build_reachability_index(snapshot),
            resource_constraints=self.query_service.build_resource_constraints(snapshot),
            environment_state=dict(snapshot.environment_state),
            performer_state=dict(snapshot.performer_state),
            active_motion=dict(snapshot.active_motion) if snapshot.active_motion else None,
            motion_artifact_refs=[dict(item) for item in snapshot.motion_artifact_refs],
            motion_constraints=dict(snapshot.motion_constraints),
            active_schedule=dict(snapshot.active_schedule) if snapshot.active_schedule else None,
            schedule_artifact_refs=[dict(item) for item in snapshot.schedule_artifact_refs],
            schedule_constraints=dict(snapshot.schedule_constraints),
            geo_anchor=snapshot.geo_anchor,
            venue_context=snapshot.venue_context,
            route_context=snapshot.route_context,
            streetview_context=snapshot.streetview_context,
            metadata=dict(snapshot.metadata),
        )

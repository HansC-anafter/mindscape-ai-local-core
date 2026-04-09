from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.services.mindscape_store import MindscapeStore

from ..schema.world_memory_delta import WorldMemoryDelta
from ..schema.world_memory_root import WorldMemoryRoot
from ..schema.world_state_snapshot import WorldStateSnapshot


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


class WorldMemoryWritebackOrchestrator:
    """Persist governed world-memory outputs into workspace state."""

    def __init__(self, *, store: Optional[MindscapeStore] = None) -> None:
        self.store = store or MindscapeStore()

    def run_for_closed_session(
        self,
        *,
        session: Any,
        workspace: Any,
        profile_id: str,
    ) -> Dict[str, Any]:
        if workspace is None or not getattr(workspace, "id", None):
            return {"updated": False, "reason": "missing_workspace"}

        session_metadata = dict(getattr(session, "metadata", {}) or {})
        packet = dict(session_metadata.get("world_memory_packet") or {})
        if not packet:
            return {"updated": False, "reason": "missing_world_memory_packet"}

        projection = dict(session_metadata.get("world_card_projection") or {})
        world_card_text = str(session_metadata.get("world_card_text") or "")
        snapshot = self._build_snapshot(
            workspace_id=workspace.id,
            profile_id=profile_id,
            project_id=getattr(session, "project_id", None),
            packet=packet,
        )

        workspace_metadata = dict(getattr(workspace, "metadata", {}) or {})
        existing_state = dict(workspace_metadata.get("world_memory_core") or {})
        history_snapshot_ids = self._append_bounded(
            existing_state.get("history_snapshot_ids"),
            snapshot.snapshot_id,
            limit=25,
        )
        source_receipt_types = self._append_unique_bounded(
            existing_state.get("source_receipt_types"),
            snapshot.source,
            limit=10,
        )
        delta = WorldMemoryDelta(
            workspace_id=workspace.id,
            snapshot_id=snapshot.snapshot_id,
            changed_fields=list(_model_dump(snapshot).keys()),
            metadata={
                "source_session_id": getattr(session, "id", None),
                "source": snapshot.source,
                "updated_at": _utc_now_iso(),
            },
        )
        delta_history = self._append_bounded(
            existing_state.get("history_deltas"),
            _model_dump(delta),
            limit=25,
        )
        root = WorldMemoryRoot(
            workspace_id=workspace.id,
            current_snapshot=snapshot,
            history_snapshot_ids=history_snapshot_ids,
            source_receipt_types=source_receipt_types,
            metadata={
                "last_session_id": getattr(session, "id", None),
                "last_project_id": getattr(session, "project_id", None),
                "last_profile_id": profile_id or None,
                "updated_at": _utc_now_iso(),
            },
            active_geo_anchor=packet.get("geo_anchor"),
        )

        workspace_metadata["world_memory_core"] = {
            "current_root": _model_dump(root),
            "latest_delta": _model_dump(delta),
            "latest_packet": deepcopy(packet),
            "latest_projection": deepcopy(projection),
            "latest_text": world_card_text,
            "history_snapshot_ids": history_snapshot_ids,
            "source_receipt_types": source_receipt_types,
            "history_deltas": delta_history,
            "last_session_id": getattr(session, "id", None),
            "updated_at": _utc_now_iso(),
        }
        workspace.metadata = workspace_metadata
        self.store.workspaces.update_workspace_sync(workspace)

        return {
            "updated": True,
            "workspace_id": workspace.id,
            "snapshot_id": snapshot.snapshot_id,
            "source": snapshot.source,
            "world_memory_root": _model_dump(root),
            "world_memory_delta": _model_dump(delta),
            "world_memory_packet": deepcopy(packet),
            "world_card_projection": deepcopy(projection),
            "world_card_text": world_card_text,
        }

    @staticmethod
    def _build_snapshot(
        *,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        packet: Dict[str, Any],
    ) -> WorldStateSnapshot:
        metadata = dict(packet.get("metadata") or {})
        if project_id and not metadata.get("project_id"):
            metadata["project_id"] = project_id
        return WorldStateSnapshot(
            snapshot_id=str(packet.get("snapshot_id") or f"wm-snap:{workspace_id}"),
            workspace_id=workspace_id,
            profile_id=profile_id or None,
            project_id=project_id or metadata.get("project_id"),
            source=str(packet.get("source") or "meeting_governed"),
            scene_id=packet.get("scene_id"),
            current_zone=packet.get("current_zone"),
            visible_objects=list(packet.get("visible_objects") or []),
            reachable_zones=list(packet.get("reachable_zones") or []),
            resource_constraints=dict(packet.get("resource_constraints") or {}),
            environment_state=dict(packet.get("environment_state") or {}),
            performer_state=dict(packet.get("performer_state") or {}),
            active_motion=dict(packet.get("active_motion") or {}) or None,
            motion_artifact_refs=[
                dict(item)
                for item in list(packet.get("motion_artifact_refs") or [])
                if isinstance(item, dict)
            ],
            motion_constraints=dict(packet.get("motion_constraints") or {}),
            geo_anchor=packet.get("geo_anchor"),
            venue_context=packet.get("venue_context"),
            route_context=packet.get("route_context"),
            streetview_context=packet.get("streetview_context"),
            metadata=metadata,
        )

    @staticmethod
    def _append_bounded(
        existing: Optional[List[Any]],
        value: Any,
        *,
        limit: int,
    ) -> List[Any]:
        values = list(existing or [])
        values.append(deepcopy(value))
        if limit > 0:
            return values[-limit:]
        return values

    @staticmethod
    def _append_unique_bounded(
        existing: Optional[List[Any]],
        value: Any,
        *,
        limit: int,
    ) -> List[Any]:
        values: List[Any] = []
        for item in list(existing or []) + [value]:
            if item in values:
                continue
            values.append(item)
        if limit > 0:
            return values[-limit:]
        return values

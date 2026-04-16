from __future__ import annotations

from typing import Any, Dict, Optional

from .world_card_projection_compiler import WorldCardProjectionCompiler
from .world_state_adapter import WorldStateAdapter


def _model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


class ContextExportFacade:
    """Facade for host-side world-context export."""

    def __init__(self):
        self.adapter = WorldStateAdapter()
        self.compiler = WorldCardProjectionCompiler()

    def export_context(
        self,
        *,
        workspace_id: str,
        governance_context: Optional[Dict[str, Any]] = None,
        memory_packet: Optional[Dict[str, Any]] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        receipt: Optional[Dict[str, Any]] = None,
        geo_context: Optional[Dict[str, Any]] = None,
        motion_context: Optional[Dict[str, Any]] = None,
        spatial_schedule_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        snapshot = self.adapter.normalize_receipt(
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            governance_context=governance_context,
            receipt=receipt,
            geo_context=geo_context,
            motion_context=motion_context,
            spatial_schedule_context=spatial_schedule_context,
        )
        root = self.adapter.build_root(snapshot)
        delta = self.adapter.build_delta(
            snapshot,
            changed_fields=list(_model_dump(snapshot).keys()),
        )
        packet = self.adapter.build_packet(snapshot)
        projection = self.compiler.compile(packet)
        projection_text = self.compiler.render_text(projection)

        return {
            "world_memory_root": _model_dump(root),
            "world_memory_delta": _model_dump(delta),
            "world_memory_packet": _model_dump(packet),
            "world_card_projection": _model_dump(projection),
            "world_card_text": projection_text,
            "receipt_source": snapshot.source,
            "session_id": session_id,
            "memory_packet_source": memory_packet or {},
            "geo_context": geo_context or {},
            "motion_context": motion_context or {},
            "spatial_schedule_context": spatial_schedule_context or {},
        }

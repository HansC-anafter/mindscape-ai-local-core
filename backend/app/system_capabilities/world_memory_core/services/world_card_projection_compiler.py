"""Render bounded world-memory packets into prompt-safe world cards."""

from __future__ import annotations

from typing import Any

from backend.app.system_capabilities.world_memory_core.schema.world_card_projection import (
    WorldCardProjection,
)
from backend.app.system_capabilities.world_memory_core.schema.world_memory_packet import (
    WorldMemoryPacket,
)


class WorldCardProjectionCompiler:
    """Project governed world-memory packets into concise text summaries."""

    def compile(self, packet: WorldMemoryPacket) -> WorldCardProjection:
        summary_lines: list[str] = []
        constraints: list[str] = []

        active_schedule = dict(packet.active_schedule or {})
        if active_schedule:
            title = str(active_schedule.get("title") or active_schedule.get("schedule_id") or "").strip()
            if title:
                summary_lines.append(f"Active schedule: {title}")
            for key, value in dict(packet.schedule_constraints or {}).items():
                formatted = self._format_constraint_value(value)
                if formatted is not None:
                    constraints.append(f"schedule_{key}={formatted}")

        performance_state = dict(packet.performance_state or {})
        if performance_state:
            performance_mode = performance_state.get("performance_mode")
            if performance_mode:
                summary_lines.append(f"Performance mode: {performance_mode}")
            preview_ready_state = performance_state.get("preview_ready_state")
            if preview_ready_state:
                summary_lines.append(f"Performance preview state: {preview_ready_state}")
            summary_lines.append(
                "Face lane: "
                f"{'active' if performance_state.get('face_lane_active') else 'inactive'} "
                f"({performance_state.get('face_source_type') or 'unknown'})"
            )
            summary_lines.append(
                "Body lane: "
                f"{'active' if performance_state.get('body_lane_active') else 'inactive'} "
                f"({performance_state.get('body_source_type') or 'unknown'})"
            )
            freshness = packet.metadata.get("performance_freshness")
            if freshness:
                summary_lines.append(f"Performance context freshness: {freshness}")

            execution_bridge = performance_state.get("execution_bridge")
            if execution_bridge:
                constraints.append(f"performance_execution_bridge={execution_bridge}")
            retarget_ready_state = performance_state.get("retarget_ready_state")
            if retarget_ready_state:
                constraints.append(f"performance_retarget_ready_state={retarget_ready_state}")

        return WorldCardProjection(
            title="World Card",
            summary_lines=summary_lines,
            constraints=constraints,
            suggested_focus=[],
            metadata=dict(packet.metadata),
        )

    def render_text(self, projection: WorldCardProjection) -> str:
        lines = [projection.title]
        lines.extend(list(projection.summary_lines or []))
        if projection.constraints:
            lines.append("Constraints:")
            lines.extend(list(projection.constraints))
        performance_run_id = projection.metadata.get("performance_source_run_id")
        if performance_run_id:
            lines.append(f"Performance run: {performance_run_id}")
        return "\n".join(line for line in lines if str(line).strip())

    @staticmethod
    def _format_constraint_value(value: Any) -> str | None:
        if value in (None, {}, []):
            return None
        if isinstance(value, list):
            return ",".join(str(item) for item in value if str(item).strip())
        return str(value)

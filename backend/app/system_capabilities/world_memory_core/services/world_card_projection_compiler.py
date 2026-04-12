from __future__ import annotations

from typing import List

from ..schema.world_card_projection import WorldCardProjection
from ..schema.world_memory_packet import WorldMemoryPacket


class WorldCardProjectionCompiler:
    """Compile prompt-safe world-card projections."""

    def compile(self, packet: WorldMemoryPacket) -> WorldCardProjection:
        summary_lines: List[str] = []
        constraints: List[str] = []
        suggested_focus: List[str] = []

        if packet.scene_id:
            summary_lines.append(f"Scene: {packet.scene_id}")
        if packet.current_zone:
            summary_lines.append(f"Zone: {packet.current_zone}")
        if packet.visible_objects:
            summary_lines.append(
                "Visible objects: " + ", ".join(packet.visible_objects[:5])
            )
        if packet.active_motion:
            motion_id = str(packet.active_motion.get("motion_id") or "").strip()
            provider = str(packet.active_motion.get("provider") or "").strip()
            status = str(packet.active_motion.get("status") or "").strip()
            duration_sec = packet.active_motion.get("duration_sec")
            fps = packet.active_motion.get("fps")
            motion_label = motion_id or provider or "motion_active"
            line = f"Active motion: {motion_label}"
            if status:
                line += f" [{status}]"
            if duration_sec is not None:
                line += f" {duration_sec}s"
            if fps is not None:
                line += f" @ {fps}fps"
            summary_lines.append(line)
        motion_freshness = str(packet.metadata.get("motion_freshness") or "").strip()
        if motion_freshness:
            summary_lines.append(f"Motion context freshness: {motion_freshness}")
        motion_source_run_id = str(packet.metadata.get("motion_source_run_id") or "").strip()
        if motion_source_run_id:
            suggested_focus.append(f"Motion run: {motion_source_run_id}")
        if packet.performance_state:
            performance_mode = str(
                packet.performance_state.get("performance_mode") or ""
            ).strip()
            if performance_mode:
                summary_lines.append(f"Performance mode: {performance_mode}")
            preview_ready_state = str(
                packet.performance_state.get("preview_ready_state") or ""
            ).strip()
            if preview_ready_state:
                summary_lines.append(
                    f"Performance preview state: {preview_ready_state}"
                )
            face_source_type = str(
                packet.performance_state.get("face_source_type") or ""
            ).strip()
            if face_source_type and face_source_type != "none":
                face_lane_state = (
                    "active"
                    if bool(packet.performance_state.get("face_lane_active"))
                    else "inactive"
                )
                summary_lines.append(
                    f"Face lane: {face_lane_state} ({face_source_type})"
                )
            body_source_type = str(
                packet.performance_state.get("body_source_type") or ""
            ).strip()
            if body_source_type and body_source_type != "none":
                body_lane_state = (
                    "active"
                    if bool(packet.performance_state.get("body_lane_active"))
                    else "inactive"
                )
                summary_lines.append(
                    f"Body lane: {body_lane_state} ({body_source_type})"
                )
        performance_freshness = str(
            packet.metadata.get("performance_freshness") or ""
        ).strip()
        if performance_freshness:
            summary_lines.append(
                f"Performance context freshness: {performance_freshness}"
            )
        performance_source_run_id = str(
            packet.metadata.get("performance_source_run_id") or ""
        ).strip()
        if performance_source_run_id:
            suggested_focus.append(f"Performance run: {performance_source_run_id}")
        if packet.geo_anchor:
            lat = packet.geo_anchor.get("lat")
            lng = packet.geo_anchor.get("lng")
            summary_lines.append(f"Geo anchor: {lat}, {lng}")
        if packet.venue_context:
            venue_name = packet.venue_context.get("name")
            venue_address = packet.venue_context.get("formatted_address")
            if venue_name:
                summary_lines.append(f"Venue: {venue_name}")
            if venue_address:
                constraints.append(f"venue_address={venue_address}")
        if packet.route_context:
            distance = packet.route_context.get("distance_meters")
            duration = packet.route_context.get("duration_seconds")
            mode = packet.route_context.get("mode")
            route_summary = f"Route({mode})"
            if distance is not None:
                route_summary += f" distance={distance}m"
            if duration is not None:
                route_summary += f" duration={duration}s"
            suggested_focus.append(route_summary)
        if packet.reachable_zones:
            suggested_focus.append(
                "Reachable zones: " + ", ".join(packet.reachable_zones[:5])
            )
        if packet.motion_artifact_refs:
            artifact_kinds = []
            for item in packet.motion_artifact_refs[:4]:
                kind = str((item or {}).get("artifact_kind") or "").strip()
                if kind:
                    artifact_kinds.append(kind)
            if artifact_kinds:
                summary_lines.append(
                    "Motion artifacts ready: " + ", ".join(artifact_kinds)
                )

        for key, value in packet.resource_constraints.items():
            constraints.append(f"{key}={value}")
        for key, value in packet.motion_constraints.items():
            constraints.append(f"motion_{key}={value}")
        motion_stale_reason = str(packet.metadata.get("motion_stale_reason") or "").strip()
        if motion_freshness:
            constraints.append(f"motion_freshness={motion_freshness}")
        if motion_stale_reason:
            constraints.append(f"motion_stale_reason={motion_stale_reason}")
        performance_execution_bridge = str(
            packet.metadata.get("performance_execution_bridge") or ""
        ).strip()
        performance_stale_reason = str(
            packet.metadata.get("performance_stale_reason") or ""
        ).strip()
        performance_retarget_ready_state = str(
            packet.performance_state.get("retarget_ready_state") or ""
        ).strip()
        if performance_freshness:
            constraints.append(f"performance_freshness={performance_freshness}")
        if performance_stale_reason:
            constraints.append(
                f"performance_stale_reason={performance_stale_reason}"
            )
        if performance_execution_bridge:
            constraints.append(
                f"performance_execution_bridge={performance_execution_bridge}"
            )
        if performance_retarget_ready_state:
            constraints.append(
                f"performance_retarget_ready_state={performance_retarget_ready_state}"
            )

        if not summary_lines:
            summary_lines.append("No explicit world scene is active yet.")

        return WorldCardProjection(
            summary_lines=summary_lines,
            constraints=constraints,
            suggested_focus=suggested_focus,
            metadata={
                "source": packet.source,
                "snapshot_id": packet.snapshot_id,
            },
        )

    def render_text(self, projection: WorldCardProjection) -> str:
        lines = [projection.title]
        lines.extend(f"- {line}" for line in projection.summary_lines)
        if projection.constraints:
            lines.append("Constraints:")
            lines.extend(f"- {line}" for line in projection.constraints)
        if projection.suggested_focus:
            lines.append("Suggested focus:")
            lines.extend(f"- {line}" for line in projection.suggested_focus)
        return "\n".join(lines)

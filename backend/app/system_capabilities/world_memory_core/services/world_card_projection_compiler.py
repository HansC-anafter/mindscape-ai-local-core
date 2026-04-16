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
        if packet.active_schedule:
            schedule_id = str(packet.active_schedule.get("schedule_id") or "").strip()
            title = str(packet.active_schedule.get("title") or "").strip()
            status = str(packet.active_schedule.get("status") or "").strip()
            segment_count = packet.active_schedule.get("segment_count")
            entity_kinds = packet.active_schedule.get("entity_kinds") or []
            schedule_label = title or schedule_id or "schedule_active"
            line = f"Active schedule: {schedule_label}"
            if status:
                line += f" [{status}]"
            if segment_count is not None:
                line += f" segments={segment_count}"
            summary_lines.append(line)
            if entity_kinds:
                suggested_focus.append(
                    "Scheduled entities: "
                    + ", ".join(str(kind) for kind in entity_kinds[:5])
                )
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
                suggested_focus.append(
                    "Motion artifacts: " + ", ".join(artifact_kinds)
                )
        if packet.schedule_artifact_refs:
            schedule_artifact_ids = []
            for item in packet.schedule_artifact_refs[:4]:
                artifact_id = str((item or {}).get("artifact_id") or "").strip()
                if artifact_id:
                    schedule_artifact_ids.append(artifact_id)
            if schedule_artifact_ids:
                suggested_focus.append(
                    "Schedule artifacts: " + ", ".join(schedule_artifact_ids)
                )

        for key, value in packet.resource_constraints.items():
            constraints.append(f"{key}={value}")
        for key, value in packet.motion_constraints.items():
            constraints.append(f"motion_{key}={value}")
        for key, value in packet.schedule_constraints.items():
            constraints.append(f"schedule_{key}={value}")

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

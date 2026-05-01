"""Normalize governed sidecars into bounded world-memory packets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.system_capabilities.world_memory_core.schema.world_memory_packet import (
    WorldMemoryPacket,
)
from backend.app.system_capabilities.world_memory_core.schema.world_state_snapshot import (
    WorldStateSnapshot,
)


class WorldStateAdapter:
    """Compile schedule and performance sidecars into a governed packet."""

    def normalize_receipt(
        self,
        *,
        workspace_id: str,
        profile_id: str,
        governance_context: Optional[Dict[str, Any]] = None,
        spatial_schedule_context: Optional[Dict[str, Any]] = None,
        performance_context: Optional[Dict[str, Any]] = None,
    ) -> WorldStateSnapshot:
        raw_schedule = dict(spatial_schedule_context or {})
        normalized_schedule = self._normalize_schedule_projection(raw_schedule)

        performance_state = self._derive_performance_state(performance_context)
        metadata = self._derive_packet_metadata(
            performance_context=performance_context,
            performance_state=performance_state,
        )

        return WorldStateSnapshot(
            workspace_id=workspace_id,
            profile_id=profile_id,
            governance_context=dict(governance_context or {}),
            active_schedule=self._derive_active_schedule(
                raw_context=raw_schedule,
                normalized_context=normalized_schedule,
            ),
            schedule_artifact_refs=self._derive_schedule_artifact_refs(
                raw_context=raw_schedule,
                normalized_context=normalized_schedule,
            ),
            schedule_constraints=self._derive_schedule_constraints(
                raw_context=raw_schedule,
                normalized_context=normalized_schedule,
            ),
            performance_state=performance_state,
            metadata=metadata,
        )

    def build_packet(self, snapshot: WorldStateSnapshot) -> WorldMemoryPacket:
        """Promote a normalized snapshot into the exported packet shape."""
        return WorldMemoryPacket(
            workspace_id=snapshot.workspace_id,
            profile_id=snapshot.profile_id,
            governance_context=dict(snapshot.governance_context),
            active_schedule=dict(snapshot.active_schedule or {})
            if snapshot.active_schedule
            else None,
            schedule_artifact_refs=[dict(ref) for ref in snapshot.schedule_artifact_refs],
            schedule_constraints=dict(snapshot.schedule_constraints),
            performance_state=dict(snapshot.performance_state or {})
            if snapshot.performance_state
            else None,
            metadata=dict(snapshot.metadata),
        )

    def _derive_active_schedule(
        self,
        *,
        raw_context: Dict[str, Any],
        normalized_context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not normalized_context:
            return None

        title = self._derive_schedule_title(raw_context, normalized_context)
        consumer_refs = []
        for consumer_code, receipt in dict(normalized_context.get("consumer_receipts") or {}).items():
            if not isinstance(receipt, dict):
                continue
            receipt_ref = dict(receipt.get("receipt_ref") or {})
            consumer_refs.append(
                {
                    "consumer_code": consumer_code,
                    "status": receipt.get("status"),
                    "receipt_artifact_id": receipt_ref.get("artifact_id"),
                }
            )

        active_schedule = {
            "schedule_id": normalized_context.get("schedule_id"),
            "status": normalized_context.get("status"),
            "title": title,
            "entity_kinds": list(normalized_context.get("entity_kinds") or []),
            "active_segments": list(normalized_context.get("active_segments") or []),
            "consumer_refs": consumer_refs,
            "revision_refs": list(normalized_context.get("schedule_revision_refs") or []),
            "updated_at": normalized_context.get("updated_at"),
        }
        time_window = raw_context.get("time_window")
        if isinstance(time_window, dict):
            active_schedule["time_window"] = dict(time_window)
        segment_count = raw_context.get("segment_count")
        if isinstance(segment_count, int):
            active_schedule["segment_count"] = segment_count
        return {
            key: value
            for key, value in active_schedule.items()
            if value not in (None, {}, [])
        }

    def _derive_schedule_artifact_refs(
        self,
        *,
        raw_context: Dict[str, Any],
        normalized_context: Optional[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        if normalized_context and isinstance(normalized_context.get("artifact_ref"), dict):
            return [dict(normalized_context["artifact_ref"])]

        artifact_refs = []
        for artifact_ref in list(raw_context.get("artifact_refs") or []):
            if not isinstance(artifact_ref, dict):
                continue
            artifact_id = str(artifact_ref.get("artifact_id") or "").strip()
            if not artifact_id:
                continue
            artifact_refs.append(
                {
                    "artifact_id": artifact_id,
                    "type": artifact_ref.get("type") or artifact_ref.get("artifact_type"),
                    "uri": artifact_ref.get("uri"),
                }
            )
        return artifact_refs

    def _derive_schedule_constraints(
        self,
        *,
        raw_context: Dict[str, Any],
        normalized_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if normalized_context and isinstance(normalized_context.get("constraint_summary"), dict):
            return dict(normalized_context["constraint_summary"])
        return dict(raw_context.get("constraint_summary") or {})

    def _normalize_schedule_projection(
        self,
        raw_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not raw_context:
            return None

        artifact_ref = self._derive_primary_artifact_ref(raw_context)
        active_segments = self._derive_active_segments(raw_context)
        consumer_receipts = self._derive_consumer_receipts(raw_context)
        revision_refs = self._derive_revision_refs(raw_context)

        normalized = {
            "schedule_id": raw_context.get("schedule_id"),
            "status": raw_context.get("status") or "planned",
            "artifact_ref": artifact_ref,
            "entity_kinds": list(raw_context.get("entity_kinds") or []),
            "active_segments": active_segments,
            "constraint_summary": dict(raw_context.get("constraint_summary") or {}),
            "consumer_receipts": consumer_receipts,
            "schedule_revision_refs": revision_refs,
            "updated_at": raw_context.get("updated_at"),
        }
        return {
            key: value
            for key, value in normalized.items()
            if value not in (None, {}, [])
        }

    @staticmethod
    def _derive_primary_artifact_ref(raw_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        artifact_ref = raw_context.get("artifact_ref")
        if isinstance(artifact_ref, dict) and artifact_ref.get("artifact_id"):
            return {
                key: value
                for key, value in {
                    "artifact_id": artifact_ref.get("artifact_id"),
                    "type": artifact_ref.get("type") or artifact_ref.get("artifact_type"),
                    "uri": artifact_ref.get("uri"),
                }.items()
                if value not in (None, "", [], {})
            }

        source_artifact_id = raw_context.get("source_artifact_id")
        if source_artifact_id:
            return {
                key: value
                for key, value in {
                    "artifact_id": source_artifact_id,
                    "type": raw_context.get("artifact_type"),
                    "uri": raw_context.get("artifact_uri"),
                }.items()
                if value not in (None, "", [], {})
            }

        for candidate in list(raw_context.get("artifact_refs") or []):
            if not isinstance(candidate, dict) or not candidate.get("artifact_id"):
                continue
            return {
                key: value
                for key, value in {
                    "artifact_id": candidate.get("artifact_id"),
                    "type": candidate.get("type") or candidate.get("artifact_type"),
                    "uri": candidate.get("uri"),
                }.items()
                if value not in (None, "", [], {})
            }
        return None

    @staticmethod
    def _derive_active_segments(raw_context: Dict[str, Any]) -> list[Dict[str, Any]]:
        active_segments = raw_context.get("active_segments")
        if isinstance(active_segments, list):
            return [dict(segment) for segment in active_segments if isinstance(segment, dict)]

        segments: list[Dict[str, Any]] = []
        for segment_id in list(raw_context.get("active_segment_ids") or []):
            normalized_segment_id = str(segment_id or "").strip()
            if not normalized_segment_id:
                continue
            segments.append(
                {
                    "segment_id": normalized_segment_id,
                    "title": normalized_segment_id,
                    "entity_refs": [],
                    "anchor_ids": [],
                }
            )
        return segments

    @staticmethod
    def _derive_consumer_receipts(raw_context: Dict[str, Any]) -> Dict[str, Any]:
        consumer_receipts = raw_context.get("consumer_receipts")
        if isinstance(consumer_receipts, dict):
            return dict(consumer_receipts)

        receipts: Dict[str, Any] = {}
        for consumer_ref in list(raw_context.get("consumer_refs") or []):
            if not isinstance(consumer_ref, dict):
                continue
            consumer_code = str(consumer_ref.get("consumer_code") or "").strip()
            if not consumer_code:
                continue
            receipts[consumer_code] = {
                "status": consumer_ref.get("status"),
                "receipt_ref": {
                    "artifact_id": consumer_ref.get("receipt_artifact_id"),
                },
            }
        return receipts

    @staticmethod
    def _derive_revision_refs(raw_context: Dict[str, Any]) -> list[Dict[str, Any]]:
        revision_refs = raw_context.get("schedule_revision_refs")
        if isinstance(revision_refs, list):
            return [dict(ref) for ref in revision_refs if isinstance(ref, dict)]

        revisions: list[Dict[str, Any]] = []
        for revision_ref in list(raw_context.get("revision_refs") or []):
            if not isinstance(revision_ref, dict):
                continue
            artifact_id = revision_ref.get("artifact_id")
            if not artifact_id:
                continue
            revisions.append(
                {
                    "schedule_id": revision_ref.get("schedule_id"),
                    "artifact_ref": {
                        key: value
                        for key, value in {
                            "artifact_id": artifact_id,
                            "type": revision_ref.get("type")
                            or revision_ref.get("artifact_type"),
                            "uri": revision_ref.get("uri"),
                        }.items()
                        if value not in (None, "", [], {})
                    },
                    "updated_at": revision_ref.get("updated_at"),
                    "relation": revision_ref.get("relation")
                    or revision_ref.get("relationship"),
                }
            )
        return revisions

    def _derive_performance_state(
        self,
        performance_context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(performance_context, dict) or not performance_context:
            return None

        freshness = self._derive_performance_freshness(performance_context)
        is_stale = freshness == "stale"
        performance_state = {
            "context_version": performance_context.get("context_version"),
            "storyboard_id": performance_context.get("storyboard_id"),
            "scene_id": performance_context.get("scene_id"),
            "performance_mode": performance_context.get("performance_mode"),
            "execution_bridge": performance_context.get("execution_bridge"),
            "preview_ready_state": "stale"
            if is_stale
            else performance_context.get("preview_ready_state"),
            "face_lane_active": False
            if is_stale
            else bool(performance_context.get("face_lane_active")),
            "face_source_type": performance_context.get("face_source_type"),
            "body_lane_active": False
            if is_stale
            else bool(performance_context.get("body_lane_active")),
            "body_source_type": performance_context.get("body_source_type"),
            "retarget_ready_state": performance_context.get("retarget_ready_state"),
            "updated_at": performance_context.get("updated_at"),
            "expires_at": performance_context.get("expires_at"),
            "source_run_id": performance_context.get("source_run_id"),
        }
        return {
            key: value
            for key, value in performance_state.items()
            if value not in (None, {}, [])
        }

    def _derive_packet_metadata(
        self,
        *,
        performance_context: Optional[Dict[str, Any]],
        performance_state: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        if performance_state:
            freshness = self._derive_performance_freshness(performance_context)
            metadata["performance_freshness"] = freshness
            if freshness == "stale":
                metadata["performance_stale_reason"] = "expired"
            source_run_id = performance_state.get("source_run_id")
            if source_run_id:
                metadata["performance_source_run_id"] = source_run_id
        return metadata

    @staticmethod
    def _derive_schedule_title(
        raw_context: Dict[str, Any],
        normalized_context: Dict[str, Any],
    ) -> str:
        raw_title = str(raw_context.get("title") or "").strip()
        if raw_title:
            return raw_title
        active_segments = list(normalized_context.get("active_segments") or [])
        if active_segments:
            first_segment = dict(active_segments[0] or {})
            title = str(first_segment.get("title") or "").strip()
            if title:
                return title
        return str(normalized_context.get("schedule_id") or "schedule").strip()

    def _derive_performance_freshness(
        self,
        performance_context: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if not isinstance(performance_context, dict):
            return None
        expires_at = self._parse_datetime(performance_context.get("expires_at"))
        if expires_at and expires_at <= datetime.now(timezone.utc):
            return "stale"
        return "fresh"

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

"""Runtime adapter for turning ObjectRefs into bounded meeting attachments."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from backend.app.models.handoff import HandoffIn
from backend.app.models.object_runtime import ObjectRef, ObjectSummary


@dataclass
class ObjectMeetingAttachmentBuildResult:
    """Generated bounded attachments and handoff envelope for one attach request."""

    context_attachments: List[dict]
    handoff_in: HandoffIn


class ObjectMeetingAttachmentService:
    """Convert resolved runtime objects into generic handoff attachments."""

    def build_handoff(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        meeting_type: str,
        intent_summary: str,
        write_mode: str,
        source_objects: Sequence[Tuple[ObjectRef, ObjectSummary]],
        target_object: Optional[Tuple[ObjectRef, ObjectSummary]] = None,
    ) -> ObjectMeetingAttachmentBuildResult:
        context_attachments: List[dict] = []

        for ref, summary in source_objects:
            context_attachments.append(
                self._build_attachment(
                    role="source",
                    verb="attach",
                    ref=ref,
                    summary=summary,
                    write_mode=write_mode,
                    target_ref=target_object[0] if target_object else None,
                )
            )

        if target_object:
            context_attachments.append(
                self._build_attachment(
                    role="target",
                    verb="attach",
                    ref=target_object[0],
                    summary=target_object[1],
                    write_mode=write_mode,
                    target_ref=None,
                )
            )

        handoff_in = HandoffIn(
            handoff_id=f"obj_attach_{uuid.uuid4().hex}",
            workspace_id=workspace_id,
            intent_summary=intent_summary,
            governance_constraints={
                "addressable_object_layer": {
                    "meeting_id": meeting_id,
                    "meeting_type": meeting_type,
                    "write_mode": write_mode,
                }
            },
            context_attachments=context_attachments,
            metadata={
                "addressable_object_layer": {
                    "meeting_id": meeting_id,
                    "meeting_type": meeting_type,
                    "write_mode": write_mode,
                    "source_object_uris": [ref.uri for ref, _ in source_objects],
                    "target_ref_uri": target_object[0].uri if target_object else None,
                }
            },
        )
        return ObjectMeetingAttachmentBuildResult(
            context_attachments=context_attachments,
            handoff_in=handoff_in,
        )

    @staticmethod
    def _build_attachment(
        *,
        role: str,
        verb: str,
        ref: ObjectRef,
        summary: ObjectSummary,
        write_mode: str,
        target_ref: Optional[ObjectRef],
    ) -> dict:
        selected_relations = []
        if target_ref:
            selected_relations.append(
                {
                    "relation_kind": "targets",
                    "to_ref": target_ref.model_dump(exclude_none=True),
                }
            )

        return {
            "attachment_id": f"att_{uuid.uuid4().hex[:16]}",
            "role": role,
            "verb": verb,
            "object_ref": ref.model_dump(exclude_none=True),
            "object_summary": {
                "title": summary.title,
                "subtitle": summary.subtitle,
                "summary_text": summary.summary_text,
                "status": summary.status,
                "labels": list(summary.labels or []),
                "owner_surface_url": summary.owner_surface_url,
            },
            "selected_relations": selected_relations,
            "owner_pack": ref.owner_pack,
            "meeting_projection": {
                "projection_type": "addressable_object_meeting_projection",
                "payload": {
                    "uri": ref.uri,
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                    "object_id": ref.object_id,
                    "title": summary.title,
                    "summary_text": summary.summary_text,
                    "labels": list(summary.labels or []),
                },
            },
            "governance_hints": {
                "write_mode": write_mode,
                "projection_level": "meeting",
            },
        }

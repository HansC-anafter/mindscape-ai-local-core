"""Runtime adapter for turning ObjectRefs into bounded meeting attachments."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from backend.app.models.handoff import HandoffIn
from backend.app.models.object_runtime import ObjectRef, ObjectSummary
from backend.app.services.object_runtime.evidence_chain import (
    build_object_attachment_evidence_chain,
)


@dataclass
class ObjectMeetingAttachmentBuildResult:
    """Generated bounded attachments and handoff envelope for one attach request."""

    context_attachments: List[dict]
    handoff_in: HandoffIn


@dataclass
class ObjectMeetingContextRecord:
    """Resolved role-bearing context object used during handoff generation."""

    role: str
    ref: ObjectRef
    summary: ObjectSummary
    meeting_projection: Optional[Dict[str, Any]]


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
        context_objects: Sequence[ObjectMeetingContextRecord],
    ) -> ObjectMeetingAttachmentBuildResult:
        context_attachments: List[dict] = []
        target_refs = [record.ref for record in context_objects if record.role == "target"]

        for record in context_objects:
            context_attachments.append(
                self._build_attachment(
                    role=record.role,
                    verb="attach",
                    ref=record.ref,
                    summary=record.summary,
                    meeting_projection=record.meeting_projection,
                    write_mode=write_mode,
                    target_refs=(
                        [target_ref for target_ref in target_refs if target_ref.uri != record.ref.uri]
                        if record.role != "target"
                        else []
                    ),
                )
            )

        role_object_uris: Dict[str, List[str]] = {}
        for record in context_objects:
            role_object_uris.setdefault(record.role, [])
            if record.ref.uri not in role_object_uris[record.role]:
                role_object_uris[record.role].append(record.ref.uri)
        evidence_chain = build_object_attachment_evidence_chain(
            context_attachments=context_attachments,
            role_object_uris=role_object_uris,
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
                    "role_object_uris": role_object_uris,
                }
            },
            context_attachments=context_attachments,
            metadata={
                "addressable_object_layer": {
                    "meeting_id": meeting_id,
                    "meeting_type": meeting_type,
                    "write_mode": write_mode,
                    "role_object_uris": role_object_uris,
                    "source_object_uris": role_object_uris.get("source", []),
                    "target_ref_uri": target_refs[0].uri if len(target_refs) == 1 else None,
                    "target_ref_uris": [target_ref.uri for target_ref in target_refs],
                    "evidence_chain": evidence_chain,
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
        meeting_projection: Optional[Dict[str, Any]],
        write_mode: str,
        target_refs: Sequence[ObjectRef],
    ) -> dict:
        selected_relations = []
        for target_ref in target_refs:
            selected_relations.append(
                {
                    "relation_kind": "targets",
                    "to_ref": target_ref.model_dump(exclude_none=True),
                }
            )

        projection_payload = (
            dict(meeting_projection)
            if isinstance(meeting_projection, dict) and meeting_projection
            else {
                "uri": ref.uri,
                "owner_pack": ref.owner_pack,
                "object_kind": ref.object_kind,
                "object_id": ref.object_id,
                "title": summary.title,
                "summary_text": summary.summary_text,
                "labels": list(summary.labels or []),
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
                "payload": projection_payload,
            },
            "governance_hints": {
                "write_mode": write_mode,
                "projection_level": "meeting",
            },
        }

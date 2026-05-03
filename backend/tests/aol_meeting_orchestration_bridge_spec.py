from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
    MeetingRequestedAction,
)
from backend.app.models.object_runtime import ObjectRef, ObjectRoleEntry, ObjectSummary
from backend.app.models.object_runtime.graph import (
    ObjectGraphProjection,
    ObjectGraphProjectResponse,
    ObjectGuidanceCard,
)
from backend.app.services.object_runtime import aol_meeting_orchestration_bridge as bridge_module
from backend.app.services.object_runtime.aol_meeting_orchestration_bridge import (
    AOLMeetingOrchestrationBridge,
)


def _ref(owner_pack: str, object_kind: str, object_id: str) -> ObjectRef:
    return ObjectRef(
        uri=f"mindscape://{owner_pack}/{object_kind}/{object_id}",
        owner_pack=owner_pack,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id="ws_demo",
    )


def _command() -> MeetingCommandRecord:
    return MeetingCommandRecord(
        command_id="cmd_demo",
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        thread_id="thread_demo",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Draft the next shot plan",
        status=MeetingCommandStatus.ACCEPTED,
    )


@pytest.mark.asyncio
async def test_bridge_projects_aol_refs_and_carries_guidance_metadata(monkeypatch):
    source_ref = _ref("ig", "reference", "ref_123")
    target_ref = _ref("creative_direction", "storyboard", "storyboard_session_1")
    calls = []

    async def _fake_project_object_graph(request, workspace_id):
        calls.append({"request": request, "workspace_id": workspace_id})
        return ObjectGraphProjectResponse(
            workspace_id=workspace_id,
            projections=[
                ObjectGraphProjection(
                    ref=source_ref,
                    summary=ObjectSummary(
                        ref=source_ref,
                        title="Reference",
                        summary_text="Reference summary",
                    ),
                    guidance=[
                        ObjectGuidanceCard(
                            id="graph-guidance",
                            title="Graph guidance",
                            metadata={
                                "recommended_pack": "creative_direction",
                                "recommended_playbook": "generate_review_asset",
                            },
                        )
                    ],
                ),
                ObjectGraphProjection(
                    ref=target_ref,
                    summary=ObjectSummary(
                        ref=target_ref,
                        title="Storyboard",
                        summary_text="Storyboard summary",
                    ),
                ),
            ],
        )

    monkeypatch.setattr(
        bridge_module,
        "project_object_graph",
        _fake_project_object_graph,
    )

    canonical = MeetingCommandEnvelope(
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Draft the next shot plan",
        context_objects=[ObjectRoleEntry(role="source", ref=source_ref)],
        requested_action=MeetingRequestedAction(
            verb="execute_playbook",
            pack_code="ig",
            playbook_code="visual_audit",
        ),
        meeting_mentions=[
            {
                "role": "target",
                "ref": target_ref.model_dump(exclude_none=True),
            }
        ],
        metadata={
            "selected_guidance_id": "selected-guidance",
            "selected_guidance_cards": [
                {
                    "id": "selected-guidance",
                    "title": "Selected guidance",
                    "metadata": {
                        "recommended_pack": "ig",
                        "recommended_playbook": "visual_audit",
                    },
                    "object_ref": source_ref.model_dump(exclude_none=True),
                }
            ],
            "selected_guidance_object_ref": source_ref.model_dump(exclude_none=True),
        },
    )

    handoff = await AOLMeetingOrchestrationBridge().build_handoff_in(
        command=_command(),
        canonical=canonical,
        session=SimpleNamespace(id="mtg_demo", meeting_type="meeting_workbench", metadata={}),
        workspace_id="ws_demo",
    )

    assert len(calls) == 1
    assert calls[0]["workspace_id"] == "ws_demo"
    assert {ref.uri for ref in calls[0]["request"].objects} == {
        source_ref.uri,
        target_ref.uri,
    }
    aol_metadata = handoff.metadata["addressable_object_layer"]
    assert aol_metadata["selected_guidance_ids"] == ["selected-guidance"]
    assert aol_metadata["selected_guidance_object_refs"] == [
        source_ref.model_dump(exclude_none=True)
    ]
    assert {
        (item["source"], item["pack_code"], item["playbook_code"])
        for item in aol_metadata["candidate_playbooks"]
    } >= {
        ("selected_pack_tool", "ig", "visual_audit"),
        ("selected_guidance", "ig", "visual_audit"),
        ("graph_guidance", "creative_direction", "generate_review_asset"),
    }
    assert any(
        attachment.get("role") == "guidance"
        and attachment.get("selected_guidance") == ["selected-guidance"]
        for attachment in handoff.context_attachments
    )
    assert handoff.governance_constraints["addressable_object_layer"] == aol_metadata
    assert handoff.playbook_requests is not None
    assert handoff.playbook_requests[0]["playbook_code"] == "visual_audit"
    assert handoff.playbook_requests[0]["request_contract_source"] == "requested_action"
    assert (
        handoff.playbook_requests[0]["input_params"]["addressable_object_layer"]
        == aol_metadata
    )


@pytest.mark.asyncio
async def test_bridge_skips_graph_projection_when_only_guidance_metadata_is_selected(monkeypatch):
    async def _unexpected_project_object_graph(request, workspace_id):
        raise AssertionError("project_object_graph should not be called without object refs")

    monkeypatch.setattr(
        bridge_module,
        "project_object_graph",
        _unexpected_project_object_graph,
    )

    handoff = await AOLMeetingOrchestrationBridge().build_handoff_in(
        command=_command(),
        canonical=MeetingCommandEnvelope(
            workspace_id="ws_demo",
            meeting_id="mtg_demo",
            intent_text="Use selected guidance",
            metadata={
                "selected_guidance_id": "guidance-only",
                "selected_guidance_metadata": {
                    "recommended_pack": "creative_direction",
                    "recommended_playbook": "generate_review_asset",
                },
            },
        ),
        session=SimpleNamespace(id="mtg_demo", meeting_type="meeting_workbench", metadata={}),
        workspace_id="ws_demo",
    )

    aol_metadata = handoff.metadata["addressable_object_layer"]
    assert aol_metadata["selected_object_refs"] == []
    assert aol_metadata["selected_guidance_ids"] == ["guidance-only"]
    assert aol_metadata["candidate_playbooks"] == [
        {
            "source": "selected_guidance",
            "pack_code": "creative_direction",
            "playbook_code": "generate_review_asset",
            "guidance_id": "guidance-only",
            "object_ref": {},
            "confidence": "hint",
            "reason": "graph guidance",
        }
    ]
    assert handoff.context_attachments[0]["role"] == "guidance"
    assert handoff.playbook_requests is None

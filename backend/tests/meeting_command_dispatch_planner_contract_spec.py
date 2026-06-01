from backend.app.models.meeting_command import MeetingCommandEnvelope
from backend.app.services.meeting_command_dispatch import should_route_meeting_orchestration


def test_force_meeting_orchestration_routes_blank_command_to_meeting_engine():
    canonical = MeetingCommandEnvelope(
        workspace_id="ws_demo",
        meeting_id="mtg_blank",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Group current yoga references into creative spaces",
        metadata={
            "force_meeting_orchestration": True,
            "active_capability_code": "ig",
            "dispatch_mode": "route_chat",
        },
    )

    assert should_route_meeting_orchestration(canonical) is True


def test_force_meeting_orchestration_can_be_carried_by_action_parameters():
    canonical = MeetingCommandEnvelope(
        workspace_id="ws_demo",
        meeting_id="mtg_blank",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Create creative spaces from current references",
        metadata={
            "dispatch_mode": "route_chat",
            "action_parameters": {
                "force_meeting_orchestration": True,
                "active_capability_code": "ig",
            },
        },
    )

    assert should_route_meeting_orchestration(canonical) is True

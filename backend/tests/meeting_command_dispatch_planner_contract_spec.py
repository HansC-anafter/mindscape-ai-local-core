from backend.app.models.meeting_command import MeetingCommandEnvelope
from backend.app.services.meeting_command_dispatch import (
    should_route_meeting_orchestration,
    should_route_playbook,
)


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


def test_motion_practice_explicit_playbook_route_wins_over_legacy_force_flag():
    canonical = MeetingCommandEnvelope(
        workspace_id="ws_demo",
        meeting_id="mtg_motion",
        origin_surface="workspace_motion_source_practice_launcher",
        actor="user",
        intent_text="AI Yoga Record + summary: create the practice record.",
        requested_action={
            "verb": "execute_playbook",
            "pack_code": "yogacoach",
            "playbook_code": "yogacoach_student_practice_summary",
            "write_mode": "recommendation_only",
            "parameters": {
                "workspace_id": "ws_demo",
                "meeting_session_id": "mtg_motion",
                "capture_session_id": "session_1",
            },
        },
        metadata={
            "dispatch_mode": "route_playbook",
            "explicit_override": True,
            "motion_practice_launch": True,
            "motion_practice_command": True,
            "force_meeting_orchestration": True,
        },
    )

    assert should_route_meeting_orchestration(canonical) is False
    assert should_route_playbook(canonical) is True

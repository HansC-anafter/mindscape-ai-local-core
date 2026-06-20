from pathlib import Path

from backend.app.models.meeting_command import MeetingCommandEnvelope
from backend.app.services import meeting_command_dispatch as facade


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO_ROOT / "backend" / "app" / "services"
SOURCE_FILES = {
    path.name: path.read_text(encoding="utf-8")
    for path in [
        SERVICE_DIR / "meeting_command_dispatch.py",
        SERVICE_DIR / "meeting_command_dispatch_routing.py",
        SERVICE_DIR / "meeting_command_dispatch_orchestration.py",
        SERVICE_DIR / "meeting_command_dispatch_actions.py",
        SERVICE_DIR / "meeting_command_dispatch_chat.py",
    ]
}


def test_facade_exposes_canonical_dispatch_contract():
    for name in [
        "_run_meeting_orchestration_in_background",
        "dispatch_meeting_orchestration_for_command",
        "dispatch_object_action_for_command",
        "dispatch_playbook_for_command",
        "dispatch_chat_for_command",
        "should_route_meeting_orchestration",
        "should_route_object_action",
        "should_route_playbook",
        "should_route_chat",
    ]:
        assert callable(getattr(facade, name))


def test_routing_predicates_stay_compatible():
    forced = MeetingCommandEnvelope(
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        intent_text="Route this through meeting orchestration.",
        metadata={
            "dispatch_mode": "route_chat",
            "action_parameters": {"force_meeting_orchestration": True},
        },
    )
    motion = MeetingCommandEnvelope(
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
            "parameters": {"meeting_session_id": "mtg_motion"},
        },
        metadata={
            "dispatch_mode": "route_playbook",
            "explicit_override": True,
            "motion_practice_launch": True,
            "force_meeting_orchestration": True,
        },
    )

    assert facade.should_route_meeting_orchestration(forced) is True
    assert facade.should_route_meeting_orchestration(motion) is False
    assert facade.should_route_playbook(motion) is True


def test_source_boundaries_keep_resource_owners_single_path():
    combined = "\n".join(SOURCE_FILES.values())

    assert all(source.count("\n") + 1 < 500 for source in SOURCE_FILES.values())
    assert SOURCE_FILES["meeting_command_dispatch.py"].count(
        "async def dispatch_meeting_orchestration_for_command"
    ) == 1
    assert SOURCE_FILES["meeting_command_dispatch_orchestration.py"].count(
        "async def dispatch_meeting_orchestration_for_command"
    ) == 1
    assert SOURCE_FILES["meeting_command_dispatch_orchestration.py"].count(
        "asyncio.wait_for("
    ) == 1
    assert all(
        "asyncio.wait_for(" not in source
        for name, source in SOURCE_FILES.items()
        if name != "meeting_command_dispatch_orchestration.py"
    )
    assert SOURCE_FILES["meeting_command_dispatch_chat.py"].count(
        "background_tasks.add_task("
    ) == 1
    assert all(
        "background_tasks.add_task(" not in source
        for name, source in SOURCE_FILES.items()
        if name != "meeting_command_dispatch_chat.py"
    )
    assert "MeetingCommandStore" in SOURCE_FILES["meeting_command_dispatch_chat.py"]
    assert "MeetingCommandStore" in SOURCE_FILES["meeting_command_dispatch_orchestration.py"]
    assert "MeetingCommandStore" not in SOURCE_FILES["meeting_command_dispatch_actions.py"]
    assert "MeetingCommandStore" not in SOURCE_FILES["meeting_command_dispatch_routing.py"]

    for token in [
        "Session(",
        "get_db",
        "commit(",
        "rollback(",
        "PgBouncer",
        "Queue",
        "Thread(",
        "Process(",
        "setInterval",
    ]:
        assert token not in combined

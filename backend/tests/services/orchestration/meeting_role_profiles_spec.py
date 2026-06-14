from pathlib import Path

from backend.app.services.orchestration.meeting.role_profiles import (
    MeetingRoleProfileResolver,
)
from backend.app.services.orchestration.meeting_agents import build_meeting_roster


def _write_role_profile_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
code: fixture_pack
meeting_role_profiles:
  - code: fixture_practice_plan
    display_name: Fixture Practice Planning
    match:
      playbook_codes: [fixture_daily_guided_practice]
      expected_outputs: [practice_sprint]
      context_object_kinds: [fixture_opportunity]
    slot_overrides:
      facilitator:
        pack_role_name: fixture_conductor
        agent_name: Fixture Conductor
        system_prompt_suffix: "Converge to one fixture sprint only."
        tool_allowlist: [fixture_pack.fixture_list_opportunities]
      planner:
        pack_role_name: fixture_mentor
        agent_name: Fixture Mentor
        tool_allowlist:
          - fixture_pack.fixture_create_practice_sprint
        capability_profile: precise
    planner_lane:
      code: fixture_practice_lane
      category_source: context_object
      categories:
        - category_id: active_opportunity
          label_selector: "$context.primary.title"
      steps:
        - step_code: create_practice_sprint
          resource_kind: practice_sprint
          effect: write
          slot: planner
""",
        encoding="utf-8",
    )


def test_resolver_selects_role_profile_from_active_pack_manifest(tmp_path, monkeypatch):
    manifest_path = (
        tmp_path
        / "backend"
        / "app"
        / "capabilities"
        / "fixture_pack"
        / "manifest.yaml"
    )
    _write_role_profile_manifest(manifest_path)
    monkeypatch.setenv("APP_DIR", str(tmp_path))

    selected = MeetingRoleProfileResolver().resolve(
        session_metadata={
            "active_capability_code": "fixture_pack",
            "meeting_role_profile_request": {
                "playbook_code": "fixture_daily_guided_practice",
                "expected_outputs": ["practice_sprint"],
                "context_object_kinds": ["fixture_opportunity"],
                "context": {"primary": {"title": "Product render practice"}},
            },
        },
    )

    assert selected is not None
    assert selected.code == "fixture_practice_plan"
    assert selected.meeting_lane_code == "fixture_practice_lane"
    assert selected.as_metadata()["pack_role_names"]["planner"] == "fixture_mentor"


def test_build_meeting_roster_applies_profile_overlay_only_when_enabled(
    tmp_path,
    monkeypatch,
):
    manifest_path = (
        tmp_path
        / "backend"
        / "app"
        / "capabilities"
        / "fixture_pack"
        / "manifest.yaml"
    )
    _write_role_profile_manifest(manifest_path)
    metadata = {
        "active_capability_code": "fixture_pack",
        "meeting_role_profile_request": {
            "playbook_code": "fixture_daily_guided_practice",
            "expected_outputs": ["practice_sprint"],
            "context_object_kinds": ["fixture_opportunity"],
            "context": {"primary": {"title": "Product render practice"}},
        },
    }
    monkeypatch.setenv("APP_DIR", str(tmp_path))

    disabled_roster = build_meeting_roster(workspace_metadata=metadata)
    assert disabled_roster["planner"].agent_name == "Planner"
    assert disabled_roster["planner"].pack_role_name is None

    monkeypatch.setenv("MEETING_ROLE_PROFILES_ENABLED", "true")
    roster = build_meeting_roster(workspace_metadata=metadata)

    assert roster["planner"].agent_id == "planner"
    assert roster["planner"].role == "planner"
    assert roster["planner"].agent_name == "Fixture Mentor"
    assert roster["planner"].pack_role_name == "fixture_mentor"
    assert roster["planner"].meeting_role_profile_code == "fixture_practice_plan"
    assert roster["planner"].meeting_lane_code == "fixture_practice_lane"
    assert roster["planner"].tools == ["fixture_pack.fixture_create_practice_sprint"]
    assert roster["facilitator"].agent_name == "Fixture Conductor"
    assert "Converge to one fixture sprint only." in (
        roster["facilitator"].system_prompt or ""
    )

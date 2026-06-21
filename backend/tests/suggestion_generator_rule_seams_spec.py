from pathlib import Path

from backend.app.services.suggestion_generator_core.suggestion_rules import (
    build_content_summary,
    check_playbook_tools_available,
    generate_fallback_suggestions,
    generate_file_suggestions,
    generate_intent_suggestions,
    generate_pack_suggestions,
    priority_score,
)


class FakeI18n:
    def t(self, namespace, key):
        return f"{namespace}:{key}"


class FakeRegistry:
    def __init__(self, tools=None):
        self.tools = tools or {}

    def get_tool(self, tool_name):
        return self.tools.get(tool_name)


def test_file_suggestions_preserve_grant_proposal_and_ocr_outputs():
    context = {"recent_file": {"name": "grant-proposal.pdf"}}
    playbooks = [
        {
            "playbook_code": "government_grant_review",
            "name": "Grant Review",
        },
        {
            "playbook_code": "major_proposal_builder",
            "name": "Proposal Builder",
        },
    ]

    suggestions = generate_file_suggestions(context, [], playbooks)

    assert [item["action"] for item in suggestions] == [
        "execute_playbook",
        "execute_playbook",
        "use_tool",
    ]
    assert suggestions[0]["params"] == {
        "playbook_code": "government_grant_review",
        "file_name": "grant-proposal.pdf",
    }
    assert suggestions[1]["side_effect_level"] == "soft_write"
    assert suggestions[2]["params"] == {
        "tool": "core_files.extract_text",
        "file_path": "grant-proposal.pdf",
    }


def test_intent_and_fallback_suggestions_use_injected_i18n():
    i18n = FakeI18n()

    missing_intent = generate_intent_suggestions({}, [], False, i18n)
    assert missing_intent == [
        {
            "title": (
                "conversation_orchestrator:"
                "suggestion.create_intent_card_title"
            ),
            "description": (
                "conversation_orchestrator:"
                "suggestion.create_intent_card_description"
            ),
            "action": "create_intent",
            "params": {},
            "cta_label": (
                "conversation_orchestrator:"
                "suggestion.create_intent_card_cta"
            ),
            "priority": "medium",
            "side_effect_level": "soft_write",
        }
    ]

    daily_planning = generate_intent_suggestions(
        {"workspace_id": "workspace-1"},
        [{"pack_id": "daily_planning", "tools_configured": True}],
        True,
        i18n,
    )
    assert daily_planning[0]["params"] == {
        "tool": "daily_planning.extract_tasks",
        "workspace_id": "workspace-1",
    }

    fallback = generate_fallback_suggestions(i18n)
    assert [item["action"] for item in fallback] == ["start_chat", "upload_file"]
    assert fallback[0]["priority"] == "low"


def test_playbook_tool_availability_uses_installed_tools_then_registry():
    installed_packs = [
        {
            "pack_id": "daily_planning",
            "tools": [{"name": "extract_tasks"}],
        }
    ]

    assert check_playbook_tools_available(
        {"tool_dependencies": ["daily_planning.extract_tasks"]},
        installed_packs,
        FakeRegistry(),
    )
    assert check_playbook_tools_available(
        {"tool_dependencies": ["research.search"]},
        installed_packs,
        FakeRegistry({"research.search": object()}),
    )
    assert not check_playbook_tools_available(
        {"tool_dependencies": ["research.search"]},
        installed_packs,
        FakeRegistry(),
    )
    assert check_playbook_tools_available({}, installed_packs, FakeRegistry())


def test_content_summary_and_pack_suggestions_preserve_limits_and_tool_names():
    timeline_items = [
        {"type": "note", "title": f"Title {idx}", "summary": f"Summary {idx}"}
        for idx in range(6)
    ]
    assistant_messages = [{"message": f"Message {idx}"} for idx in range(4)]

    summary = build_content_summary(
        timeline_items,
        assistant_messages,
        "x" * 240,
    )

    assert "Workspace Focus: " + ("x" * 200) in summary
    assert "Title 4" in summary
    assert "Title 5" not in summary
    assert "Message 2" in summary
    assert "Message 3" not in summary

    suggestions = generate_pack_suggestions(
        {
            "workspace_focus": "launch plan",
            "workspace_id": "workspace-1",
        },
        [
            {
                "pack_id": "content_drafting",
                "tools_configured": True,
                "side_effect_level": "soft_write",
            },
            {"pack_id": "research", "tools_configured": True},
            {"pack_id": "semantic_seeds", "tools_configured": True},
        ],
    )

    assert [item["params"]["tool"] for item in suggestions] == [
        "content_drafting.generate",
        "research.search",
        "semantic_seeds.extract_seeds",
    ]
    assert suggestions[0]["side_effect_level"] == "soft_write"
    assert priority_score("high") > priority_score("medium") > priority_score("low")
    assert priority_score("unknown") == 0


def test_suggestion_generator_rule_files_stay_below_line_gate():
    repo_root = Path(__file__).resolve().parents[2]
    paths = [
        repo_root / "backend/app/services/suggestion_generator.py",
        repo_root / "backend/app/services/suggestion_generator_core/__init__.py",
        repo_root / "backend/app/services/suggestion_generator_core/suggestion_rules.py",
        repo_root / "backend/tests/suggestion_generator_rule_seams_spec.py",
    ]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path


def test_suggestion_rules_have_no_resource_access_markers():
    repo_root = Path(__file__).resolve().parents[2]
    source = (
        repo_root
        / "backend/app/services/suggestion_generator_core/suggestion_rules.py"
    ).read_text()
    markers = [
        "Mindscape" + "Store",
        "InstalledPacks" + "Store",
        "Playbook" + "Service",
        "Config" + "Store",
        "create_llm_provider" + "_manager",
        "ModelRoutingPolicy" + "Service",
        "extract" + "(",
        "session" + "maker",
        "create" + "_engine",
        "Pg" + "Bouncer",
        "create" + "_task",
        "Queue" + "(",
        "Thread" + "(",
        "Process" + "(",
        "red" + "is",
        "poll" + "ing",
        "Event" + "Source",
        "Web" + "Socket",
        "web" + "socket",
        "set" + "Interval",
        "set" + "Timeout",
        "work" + "er",
    ]

    assert not [marker for marker in markers if marker in source]

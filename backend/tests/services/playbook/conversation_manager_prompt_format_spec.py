import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

from backend.app.services.playbook.conversation_manager import PlaybookConversationManager
from backend.app.services.playbook.conversation_manager_core import (
    build_base_prompt_parts,
    build_tool_access_sections,
    build_tool_result_message,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
SERVICE_PATH = REPO_ROOT / "backend/app/services/playbook/conversation_manager.py"
CORE_DIR = REPO_ROOT / "backend/app/services/playbook/conversation_manager_core"
PROMPT_CORE_PATH = CORE_DIR / "prompt_formatting.py"
PARSER_SPEC_PATH = REPO_ROOT / "backend/tests/test_conversation_manager_tool_call_parser.py"
TOUCHED_PATHS = [
    SERVICE_PATH,
    CORE_DIR / "__init__.py",
    CORE_DIR / "tool_call_parser.py",
    PROMPT_CORE_PATH,
    Path(__file__),
    PARSER_SPEC_PATH,
]


def _fake_playbook():
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name="Launch SOP",
            playbook_code="launch.sop",
        ),
        sop_content="1. Review inputs\n2. Produce draft",
    )


def _resource_markers():
    return [
        "Mindscape" + "Store",
        "get_tool" + "_slot_info_collector",
        "collect" + "_slot_info",
        "format" + "_for_prompt",
        "get_mindscape" + "_tool",
        "_tool" + "_executor",
        "session" + "maker",
        "create" + "_engine",
        "Pg" + "Bouncer",
        "work" + "er",
        "que" + "ue",
        "poll" + "ing",
        "web" + "socket",
        "Event" + "Source",
        "request" + "s",
        "http" + "x",
        "Fast" + "API",
        "API" + "Router",
        "store" + ".",
    ]


def test_base_prompt_parts_preserve_playbook_variant_user_context_and_auto_execute_marker():
    parts = build_base_prompt_parts(
        playbook_name="Launch SOP",
        sop_content="1. Review inputs",
        user_context={
            "identity": "operator",
            "solving": "ship beta",
            "thinking": "scope risk",
        },
        target_language="en",
        variant={"id": "fast"},
        skip_steps=[2, 4],
        custom_checklist=["Confirm acceptance"],
        auto_execute=True,
    )
    prompt = "\n".join(parts)

    assert "[PLAYBOOK: Launch SOP]" in prompt
    assert "Skip the following steps: 2, 4" in prompt
    assert "- Confirm acceptance" in prompt
    assert "Identity: operator" in prompt
    assert "Always respond in en." in prompt
    assert "\u26a1 **AUTO-EXECUTE MODE ENABLED**:" in prompt


def test_tool_access_sections_prefer_slots_and_keep_cached_fallback():
    sections = build_tool_access_sections(
        slot_info_str="[TOOL_SLOT]\nslot details\n[/TOOL_SLOT]",
        cached_tools_str="filesystem_read_file(path)",
    )
    text = "\n".join(sections)

    assert text.index("[TOOL_SLOT]") < text.index("## Tool Call Format")
    assert "Format A (Use Tool Slot, Recommended)" in text
    assert "If no suitable slot is available" in text
    assert "filesystem_read_file(path)" in text


def test_tool_result_message_formats_success_failure_schema_and_auto_execute_continuation():
    message = build_tool_result_message(
        tool_results=[
            {
                "tool_name": "filesystem_read_file",
                "success": True,
                "result": {"content": "ok"},
            },
            {
                "tool_name": "filesystem_write_file",
                "success": False,
                "error": "missing file_path",
            },
        ],
        tool_schemas={
            "filesystem_write_file": {
                "name": "filesystem_write_file",
                "description": "Write a file",
                "input_schema": {
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Target path",
                        }
                    },
                    "required": ["file_path"],
                },
            }
        },
        auto_execute=True,
    )

    assert "Execution successful" in message
    assert '"content": "ok"' in message
    assert "missing file_path" in message
    assert "`file_path` (string) (required): Target path" in message
    assert "\u26a1 AUTO-EXECUTE MODE" in message


def test_public_conversation_manager_uses_prompt_helpers_without_workspace_resource_calls():
    profile = SimpleNamespace(
        self_description={
            "identity": "operator",
            "solving": "launch",
            "thinking": "timeline",
        }
    )
    manager = PlaybookConversationManager(
        playbook=_fake_playbook(),
        profile=profile,
        locale="en",
        workspace_id=None,
        auto_execute=True,
    )
    manager.cached_tools_str = "filesystem_list_files(path)"

    prompt = asyncio.run(manager.build_system_prompt())

    assert "[PLAYBOOK: Launch SOP]" in prompt
    assert "filesystem_list_files(path)" in prompt
    assert "\u26a1 **AUTO-EXECUTE MODE ENABLED**:" in prompt
    assert "Format A (Use Tool Slot, Recommended)" not in prompt


def test_conversation_manager_prompt_files_stay_below_line_gate():
    for path in TOUCHED_PATHS:
        assert len(path.read_text().splitlines()) <= 500, path


def test_conversation_manager_prompt_core_has_no_resource_markers():
    scanned_text = "\n".join([PROMPT_CORE_PATH.read_text(), Path(__file__).read_text()])
    for marker in _resource_markers():
        assert marker not in scanned_text, marker


def test_conversation_manager_resource_owners_remain_in_public_service_only():
    service_text = SERVICE_PATH.read_text()
    prompt_core_text = PROMPT_CORE_PATH.read_text()
    required_public_markers = [
        "Mindscape" + "Store",
        "get_tool" + "_slot_info_collector",
        "collect" + "_slot_info",
        "format" + "_for_prompt",
        "get_mindscape" + "_tool",
        "_tool" + "_executor",
        "store" + ".get_profile",
    ]

    for marker in required_public_markers:
        assert marker in service_text, marker
        assert marker not in prompt_core_text, marker


def test_conversation_manager_touched_sources_are_ascii_only():
    pattern = re.compile(r"[^\x00-\x7f]")
    for path in TOUCHED_PATHS:
        assert not pattern.search(path.read_text()), path

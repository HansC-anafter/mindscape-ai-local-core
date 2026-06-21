"""Focused tests for shared prompt template seams."""

from pathlib import Path

from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.shared import prompt_templates as public_module
from backend.app.shared.prompt_templates_language import (
    build_language_policy_section,
    get_language_name,
)
from backend.app.shared.prompt_templates_modes import (
    build_agent_mode_prompt,
    build_execution_mode_prompt,
)
from backend.app.shared.prompt_templates_runtime_profile import (
    build_runtime_profile_prompt,
)
from backend.app.shared.prompt_templates_workspace import build_workspace_context_prompt


REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET = REPO_ROOT / "backend/app/shared/prompt_templates.py"
SEAMS = [
    REPO_ROOT / "backend/app/shared/prompt_templates_language.py",
    REPO_ROOT / "backend/app/shared/prompt_templates_workspace.py",
    REPO_ROOT / "backend/app/shared/prompt_templates_modes.py",
    REPO_ROOT / "backend/app/shared/prompt_templates_runtime_profile.py",
]
SPEC = REPO_ROOT / "backend/tests/shared/prompt_templates_seams_spec.py"


def test_public_facade_aliases_private_prompt_seams():
    assert public_module.get_language_name is get_language_name
    assert public_module.build_language_policy_section is build_language_policy_section
    assert public_module.build_workspace_context_prompt is build_workspace_context_prompt
    assert public_module.build_execution_mode_prompt is build_execution_mode_prompt
    assert public_module.build_agent_mode_prompt is build_agent_mode_prompt
    assert public_module.build_runtime_profile_prompt is build_runtime_profile_prompt


def test_representative_prompt_markers_are_preserved():
    playbooks = [
        {
            "playbook_code": "content_drafting",
            "name": "Content Drafting",
            "description": "Draft documents and export .docx files.",
            "output_type": ".docx",
            "output_types": [".docx"],
            "tags": ["file-export", "document"],
        }
    ]

    assert get_language_name("zh-TW") == "Traditional Chinese"
    language_policy = public_module.build_language_policy_section("zh-TW")
    assert "[LANGUAGE_POLICY]" in language_policy
    assert "Traditional Chinese" in language_policy

    workspace_prompt = public_module.build_workspace_context_prompt(
        preferred_language="zh-TW",
        available_playbooks=playbooks,
    )
    assert "Workspace File Export Capabilities" in workspace_prompt
    assert "content_drafting" in workspace_prompt

    execution_prompt = public_module.build_execution_mode_prompt(
        preferred_language="en",
        available_playbooks=playbooks,
        expected_artifacts=["docx"],
        execution_priority="high",
    )
    assert "**Execution Priority: HIGH**" in execution_prompt
    assert "docx" in execution_prompt

    agent_prompt = public_module.build_agent_mode_prompt(
        preferred_language="zh-TW",
        available_playbooks=playbooks,
        expected_artifacts=["pptx"],
    )
    assert "Every response must have TWO parts" in agent_prompt
    assert "Available Playbooks" in agent_prompt

    runtime_prompt = public_module.build_runtime_profile_prompt(
        WorkspaceRuntimeProfile()
    )
    assert "[RUNTIME_PROFILE]" in runtime_prompt
    assert "**Recovery Policy (Phase 2):**" in runtime_prompt


def test_prompt_template_files_stay_below_line_gate():
    for path in [TARGET, *SEAMS, SPEC]:
        assert len(path.read_text().splitlines()) <= 500, path


def test_prompt_template_seams_do_not_add_executable_resource_markers():
    text = "\n".join(path.read_text() for path in [TARGET, *SEAMS])
    markers = [
        "session" + "maker",
        "create_" + "engine",
        "Pg" + "Bouncer",
        "create_" + "task",
        "Q" + "ueue(",
        "Th" + "read(",
        "Pro" + "cess(",
        "re" + "dis",
        "po" + "ll" + "ing",
        "Event" + "Source",
        "Web" + "Socket",
        "web" + "socket",
        "set" + "Interval",
        "set" + "Timeout",
        "ht" + "tpx",
        "req" + "uests.",
        "sub" + "process",
        "Fast" + "API",
        "API" + "Router",
    ]

    assert [marker for marker in markers if marker in text] == []

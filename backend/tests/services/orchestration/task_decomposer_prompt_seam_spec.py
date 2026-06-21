"""Focused tests for the task decomposer prompt seam."""

from pathlib import Path

from backend.app.services.orchestration import task_decomposer as public_module
from backend.app.services.orchestration.task_decomposer_core import (
    DECOMPOSE_SYSTEM_PROMPT,
    EXTEND_SYSTEM_PROMPT,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
TARGET = REPO_ROOT / "backend/app/services/orchestration/task_decomposer.py"
CORE_DIR = REPO_ROOT / "backend/app/services/orchestration/task_decomposer_core"
SPEC = REPO_ROOT / "backend/tests/services/orchestration/task_decomposer_prompt_seam_spec.py"


def test_task_decomposer_prompt_aliases_point_to_private_templates():
    assert public_module._DECOMPOSE_SYSTEM_PROMPT is DECOMPOSE_SYSTEM_PROMPT
    assert public_module._EXTEND_SYSTEM_PROMPT is EXTEND_SYSTEM_PROMPT


def test_task_decomposer_prompt_templates_keep_required_placeholders():
    assert "{max_phases}" in DECOMPOSE_SYSTEM_PROMPT
    assert "{playbooks}" in DECOMPOSE_SYSTEM_PROMPT
    assert "{tools}" in DECOMPOSE_SYSTEM_PROMPT
    assert "{wave_results}" in EXTEND_SYSTEM_PROMPT
    assert "{existing_phase_ids}" in EXTEND_SYSTEM_PROMPT
    assert "{playbooks}" in EXTEND_SYSTEM_PROMPT


def test_task_decomposer_files_stay_below_line_gate():
    paths = [TARGET, CORE_DIR / "__init__.py", CORE_DIR / "prompt_templates.py", SPEC]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path


def test_task_decomposer_touched_sources_have_no_chinese_or_emoji():
    paths = [TARGET, CORE_DIR / "__init__.py", CORE_DIR / "prompt_templates.py", SPEC]
    for path in paths:
        text = path.read_text()
        assert not any("\u4e00" <= char <= "\u9fff" for char in text), path
        assert not any("\U0001f600" <= char <= "\U0001f64f" for char in text), path


def test_task_decomposer_core_has_no_shared_resource_markers():
    text = "\n".join(path.read_text() for path in CORE_DIR.glob("*.py"))
    markers = [
        "Mindscape" + "Store",
        "session" + "maker",
        "create_" + "engine",
        "Pg" + "Bouncer",
        "create_" + "task",
        "Q" + "ueue(",
        "Th" + "read(",
        "Pro" + "cess(",
        "re" + "dis",
        "poll" + "ing",
        "Event" + "Source",
        "Web" + "Socket",
        "web" + "socket",
        "set" + "Interval",
        "set" + "Timeout",
        "work" + "er",
        "ht" + "tpx",
        "req" + "uests",
        "sl" + "eep",
        "Fast" + "API",
        "API" + "Router",
    ]

    assert [marker for marker in markers if marker in text] == []

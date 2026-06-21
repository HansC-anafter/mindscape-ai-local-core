from pathlib import Path
import re

from backend.app.services.playbook.tool_slot_info_collector import (
    ToolSlotInfo,
    ToolSlotInfoCollector,
)
from backend.app.services.playbook.tool_slot_info_core.prompt_formatting import (
    format_slot_info_for_prompt,
)
from backend.app.services.playbook.tool_slot_info_core.types import (
    ToolSlotInfo as PrivateToolSlotInfo,
)


REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / ".git").exists() and (parent / "backend/app").exists()
)
SOURCE_PATHS = [
    REPO_ROOT / "backend/app/services/playbook/tool_slot_info_collector.py",
    REPO_ROOT / "backend/app/services/playbook/tool_slot_info_core/__init__.py",
    REPO_ROOT / "backend/app/services/playbook/tool_slot_info_core/types.py",
    REPO_ROOT / "backend/app/services/playbook/tool_slot_info_core/prompt_formatting.py",
]
RESOURCE_MARKER_TERMS = (
    "Mindscape" + "Store",
    "ToolSlot" + "Mappings" + "Store",
    "Tool" + "Embedding" + "Service",
    "Tool" + "List" + "Service",
    "get_tool_slot_" + "resolver",
    "db" + "_path",
    "core_" + "l" + "lm" + "_call",
    "l" + "lm",
    "Pg" + "Bouncer",
    "Queue" + "(",
    "Thread" + "(",
    "Process" + "(",
    "poll" + "ing",
    "web" + "socket",
    "http" + "x",
    "request" + "s",
    "slee" + "p",
    "Fast" + "API",
    "API" + "Router",
)
RESOURCE_MARKERS = re.compile("|".join(re.escape(term) for term in RESOURCE_MARKER_TERMS))
SOURCE_LANGUAGE_MARKERS = re.compile(
    r"[\u4e00-\u9fff]|[\U0001f600-\U0001f64f]"
)


def _info(slot: str, source: str, priority: int, relevance: float = 0.0):
    return ToolSlotInfo(
        slot=slot,
        description=f"Description for {slot}",
        source=source,
        priority=priority,
        relevance_score=relevance,
        mapped_tool_id=f"mapped.{slot}",
    )


def test_public_tool_slot_info_reexport_matches_private_type():
    assert ToolSlotInfo is PrivateToolSlotInfo


def test_public_collector_format_for_prompt_delegates_to_private_formatter():
    slot_info_map = {
        "tool.alpha": _info("tool.alpha", "playbook", 90),
        "tool.beta": _info("tool.beta", "workspace", 50),
    }
    collector = ToolSlotInfoCollector(store=object())

    assert collector.format_for_prompt(slot_info_map) == format_slot_info_for_prompt(
        slot_info_map=slot_info_map,
        include_policy=True,
        include_mapped_tool=True,
        include_relevance_score=False,
    )


def test_prompt_formatter_orders_sections_by_priority_and_relevance():
    slot_info_map = {
        "tool.low": _info("tool.low", "playbook", 80, 0.99),
        "tool.tie_a": _info("tool.tie_a", "playbook", 90, 0.10),
        "tool.tie_b": _info("tool.tie_b", "playbook", 90, 0.80),
        "tool.project": _info("tool.project", "project", 70, 0.20),
    }

    rendered = format_slot_info_for_prompt(
        slot_info_map=slot_info_map,
        include_relevance_score=True,
    )

    assert rendered.index("- **tool.tie_b**") < rendered.index("- **tool.tie_a**")
    assert rendered.index("- **tool.tie_a**") < rendered.index("- **tool.low**")
    assert rendered.index("## Priority Use") < rendered.index("## Project Level")
    assert "  - Relevance: 0.80" in rendered
    assert "  - Mapped to: mapped.tool.project" in rendered


def test_tool_slot_info_collector_prompt_files_stay_below_line_gate():
    touched_paths = SOURCE_PATHS + [Path(__file__)]
    over_limit = {
        str(path.relative_to(REPO_ROOT)): len(path.read_text().splitlines())
        for path in touched_paths
        if len(path.read_text().splitlines()) > 500
    }
    assert over_limit == {}


def test_tool_slot_info_core_has_no_resource_markers():
    matches = {
        path.name: RESOURCE_MARKERS.findall(path.read_text())
        for path in SOURCE_PATHS
        if "tool_slot_info_core" in str(path)
    }
    assert matches == {
        path.name: [] for path in SOURCE_PATHS if "tool_slot_info_core" in str(path)
    }


def test_tool_slot_info_touched_sources_have_no_chinese_or_emoji():
    touched_paths = SOURCE_PATHS + [Path(__file__)]
    matches = {
        path.name: SOURCE_LANGUAGE_MARKERS.findall(path.read_text())
        for path in touched_paths
    }
    assert matches == {path.name: [] for path in touched_paths}

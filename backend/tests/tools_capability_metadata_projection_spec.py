from backend.app.routes.core.tools.base import (
    _overlay_registered_tool_policy_metadata,
    _registered_tool_from_capability_tool_info,
    _registered_tool_from_manifest_tool,
    _tool_info_has_policy_metadata,
)
from backend.app.models.tool_registry import RegisteredTool
from backend.app.services.tool_list_service import ToolInfo


def test_manifest_capability_tool_projection_preserves_readonly_metadata() -> None:
    tool = _registered_tool_from_manifest_tool(
        capability_code="ig",
        tool_cfg={
            "code": "ig_query_references",
            "description": "Query references.",
            "read_only": True,
            "side_effect_level": "none",
            "risk_class": "readonly",
            "planner_contract": {"effect": "read"},
        },
    )

    assert tool is not None
    assert tool.tool_id == "ig.ig_query_references"
    assert tool.read_only is True
    assert tool.side_effect_level == "none"
    assert tool.risk_class == "readonly"
    assert tool.capability_code == "ig"


def test_existing_registry_tool_can_overlay_manifest_policy_metadata() -> None:
    existing_tool = RegisteredTool(
        tool_id="ig.ig_query_references",
        site_id="capability",
        provider="capability",
        display_name="ig_query_references",
        origin_capability_id="ig.ig_query_references",
        category="capability",
        description="Stale registry copy.",
        endpoint="",
        methods=[],
        enabled=True,
        read_only=False,
        side_effect_level="none",
        capability_code="",
        risk_class="readonly",
    )
    manifest_tool_info = ToolInfo(
        tool_id="ig.ig_query_references",
        name="ig_query_references",
        description="Query references.",
        category="capability",
        source="capability",
        enabled=True,
        metadata={
            "tool_info": {
                "capability": "ig",
                "tool_name": "ig_query_references",
                "tool_info": {
                    "code": "ig_query_references",
                    "read_only": True,
                    "risk_class": "readonly",
                    "side_effect_level": "none",
                },
            }
        },
    )

    assert _tool_info_has_policy_metadata(manifest_tool_info) is True
    manifest_tool = _registered_tool_from_capability_tool_info(manifest_tool_info)
    _overlay_registered_tool_policy_metadata(existing_tool, manifest_tool)

    assert existing_tool.read_only is True
    assert existing_tool.side_effect_level == "none"
    assert existing_tool.risk_class == "readonly"
    assert existing_tool.capability_code == "ig"


def test_capability_tool_info_projection_derives_readonly_from_planner_contract() -> None:
    tool_info = ToolInfo(
        tool_id="ig.ig_query_references",
        name="ig_query_references",
        description="Query references.",
        category="capability",
        source="capability",
        enabled=True,
        metadata={
            "tool_info": {
                "capability": "ig",
                "tool_name": "ig_query_references",
                "tool_info": {
                    "code": "ig_query_references",
                    "planner_contract": {"effect": "read"},
                },
            }
        },
    )

    tool = _registered_tool_from_capability_tool_info(tool_info)

    assert tool.read_only is True
    assert tool.side_effect_level == "none"
    assert tool.risk_class == "readonly"
    assert tool.capability_code == "ig"

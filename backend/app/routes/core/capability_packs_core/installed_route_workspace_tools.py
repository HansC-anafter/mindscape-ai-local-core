from typing import Any, Callable, Dict, List

from fastapi import HTTPException

from .manifest_scan import _WORKSPACE_TOOL_ID_PATTERN

_WORKSPACE_TOOL_SLOTS = {
    "workspace.right_rail.tool",
    "workbench.left_tool_rail",
    "aol.runtime.command_surface",
}

FormatUiComponent = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def _planner_exposed_tool_codes(pack_meta: Dict[str, Any]) -> set[str]:
    exposed_codes: set[str] = set()
    for tool in pack_meta.get("tools", []) or []:
        if not isinstance(tool, dict):
            continue
        code = str(tool.get("code") or tool.get("name") or "").strip()
        planner_contract = tool.get("planner_contract")
        if (
            code
            and isinstance(planner_contract, dict)
            and planner_contract.get("exposed") is True
        ):
            exposed_codes.add(code)
    return exposed_codes


def _normalize_workspace_tool_aol(
    tool: Dict[str, Any],
    index: int,
) -> Dict[str, str] | None:
    aol = tool.get("aol")
    if aol is None:
        return None
    if not isinstance(aol, dict):
        raise HTTPException(
            status_code=422,
            detail=f"workspace_tools[{index}].aol must be an object",
        )
    object_kind = str(aol.get("object_kind") or "").strip()
    object_uri = str(aol.get("object_uri") or "").strip()
    role = str(aol.get("role") or "").strip()
    if not object_kind or not object_uri or not role:
        raise HTTPException(
            status_code=422,
            detail=(
                f"workspace_tools[{index}].aol must include object_kind, "
                "object_uri, and role"
            ),
        )
    return {
        "object_kind": object_kind,
        "object_uri": object_uri,
        "role": role,
    }


def build_capability_workspace_tools(
    *,
    capability_code: str,
    pack_meta: Dict[str, Any],
    format_ui_component: FormatUiComponent,
) -> List[Dict[str, Any]]:
    ui_components = pack_meta.get("ui_components", [])
    components_by_code = {
        component.get("code"): component
        for component in ui_components
        if isinstance(component, dict) and component.get("code")
    }
    exposed_tool_codes = _planner_exposed_tool_codes(pack_meta)
    formatted_tools = []
    seen_ids = set()
    for index, tool in enumerate(pack_meta.get("workspace_tools", []) or []):
        if not isinstance(tool, dict):
            raise HTTPException(
                status_code=422,
                detail=f"workspace_tools[{index}] must be an object",
            )
        tool_id = str(tool.get("id") or "").strip()
        group = str(tool.get("group") or "").strip()
        slot = str(tool.get("slot") or "workspace.right_rail.tool").strip()
        label = tool.get("label")
        icon = tool.get("icon")
        panel_component_code = str(tool.get("panel_component_code") or "").strip()
        shortcut = tool.get("shortcut")
        runtime_tool_code = tool.get("runtime_tool_code")
        state_schema = tool.get("state_schema")
        order = tool.get("order")
        if not _WORKSPACE_TOOL_ID_PATTERN.match(tool_id) or tool_id in seen_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"workspace_tools[{index}].id must match ^[a-z0-9_]+$ "
                    "and be unique"
                ),
            )
        if group != "capability":
            raise HTTPException(
                status_code=422,
                detail=f"workspace_tools[{index}].group must be capability",
            )
        if slot not in _WORKSPACE_TOOL_SLOTS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"workspace_tools[{index}].slot must be one of "
                    f"{sorted(_WORKSPACE_TOOL_SLOTS)}"
                ),
            )
        if not isinstance(label, str) or not label.strip():
            raise HTTPException(
                status_code=422,
                detail=f"workspace_tools[{index}].label must be a non-empty string",
            )
        if not isinstance(icon, str) or not icon.strip():
            raise HTTPException(
                status_code=422,
                detail=f"workspace_tools[{index}].icon must be a non-empty string",
            )
        if type(order) is not int:
            raise HTTPException(
                status_code=422,
                detail=f"workspace_tools[{index}].order must be an integer",
            )
        if shortcut is not None and (
            not isinstance(shortcut, str) or not shortcut.strip()
        ):
            raise HTTPException(
                status_code=422,
                detail=(f"workspace_tools[{index}].shortcut must be a non-empty string"),
            )
        if runtime_tool_code is not None:
            if not isinstance(runtime_tool_code, str) or not runtime_tool_code.strip():
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"workspace_tools[{index}].runtime_tool_code must be a "
                        "non-empty string"
                    ),
                )
            runtime_tool_code = runtime_tool_code.strip()
            if runtime_tool_code not in exposed_tool_codes:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"workspace_tools[{index}].runtime_tool_code "
                        f"'{runtime_tool_code}' must reference an exposed "
                        "planner_contract tool"
                    ),
                )
        if state_schema is not None and not isinstance(state_schema, dict):
            raise HTTPException(
                status_code=422,
                detail=f"workspace_tools[{index}].state_schema must be an object",
            )
        panel_component = components_by_code.get(panel_component_code)
        if not panel_component:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"workspace_tools[{index}].panel_component_code "
                    f"'{panel_component_code}' does not match ui_components[].code"
                ),
            )
        aol = _normalize_workspace_tool_aol(tool, index)
        seen_ids.add(tool_id)
        formatted_tool = {
            "tool_key": f"{pack_meta.get('code') or capability_code}:{tool_id}",
            "capability_code": pack_meta.get("code") or capability_code,
            "id": tool_id,
            "group": group,
            "slot": slot,
            "label": label.strip(),
            "icon": icon.strip(),
            "order": order,
            "panel_component_code": panel_component_code,
            "panel_component": format_ui_component(
                capability_code,
                panel_component,
            ),
        }
        if isinstance(shortcut, str) and shortcut.strip():
            formatted_tool["shortcut"] = shortcut.strip()
        if runtime_tool_code:
            formatted_tool["runtime_tool_code"] = runtime_tool_code
        if aol:
            formatted_tool["aol"] = aol
        if isinstance(state_schema, dict):
            formatted_tool["state_schema"] = state_schema
        formatted_tools.append(formatted_tool)

    return sorted(formatted_tools, key=lambda item: (item["order"], item["tool_key"]))

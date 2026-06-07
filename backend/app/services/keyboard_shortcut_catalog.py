"""
Keyboard shortcut catalog helpers.
"""

from typing import Any, Dict, List

from backend.app.routes.core.capability_packs_core.manifest_scan import (
    _get_installed_pack_ids,
    _scan_pack_yaml_files,
)


def build_keyboard_shortcut_catalog() -> List[Dict[str, Any]]:
    """
    Build a bounded catalog from installed capability workspace tools.

    Returns:
        Stable catalog entries for settings and shortcut profile validation.
    """
    installed_ids = _get_installed_pack_ids()
    catalog: List[Dict[str, Any]] = []

    for pack_meta in _scan_pack_yaml_files():
        pack_id = str(pack_meta.get("id") or "").strip()
        if not pack_id or pack_id not in installed_ids:
            continue

        capability_code = str(pack_meta.get("code") or pack_id).strip()
        if not capability_code:
            continue

        display_name = str(
            pack_meta.get("display_name")
            or pack_meta.get("name")
            or capability_code
        ).strip()

        for tool in pack_meta.get("workspace_tools", []) or []:
            if not isinstance(tool, dict):
                continue
            tool_id = str(tool.get("id") or "").strip()
            label = str(tool.get("label") or tool_id).strip()
            if not tool_id or not label:
                continue

            tool_key = f"{capability_code}:{tool_id}"
            shortcut = tool.get("shortcut")
            catalog.append(
                {
                    "binding_id": f"workspace_tool:{tool_key}:open",
                    "command_id": "pack.workspace_tool.open",
                    "label": label,
                    "owner_type": "pack",
                    "owner_id": capability_code,
                    "owner_label": display_name,
                    "default_shortcut": shortcut.strip()
                    if isinstance(shortcut, str) and shortcut.strip()
                    else None,
                    "scope": "workbench",
                    "source": "manifest.workspace_tools",
                    "metadata": {
                        "tool_key": tool_key,
                        "tool_id": tool_id,
                        "capability_code": capability_code,
                        "slot": str(
                            tool.get("slot") or "workspace.right_rail.tool"
                        ).strip(),
                    },
                }
            )

    return sorted(
        catalog,
        key=lambda item: (
            str(item.get("owner_id") or ""),
            str(item.get("label") or ""),
            str(item.get("binding_id") or ""),
        ),
    )

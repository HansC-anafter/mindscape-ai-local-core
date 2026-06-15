from typing import Any, Dict, List


def _normalize_string_list(values: Any) -> List[str]:
    normalized: List[str] = []
    seen = set()
    if not isinstance(values, list):
        return normalized
    for value in values:
        candidate = str(value or "").strip()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return normalized


def _is_main_page_component(component: Dict[str, Any]) -> bool:
    code = str(component.get("code") or "").strip()
    if not code:
        return False
    return (
        code.endswith("Page")
        or code.endswith("StudioPage")
        or code.endswith("Workbench")
    )


def _resolve_host_route_template(pack_meta: Dict[str, Any], capability_code: str) -> str | None:
    for surface in pack_meta.get("ui_surfaces", []) or []:
        if not isinstance(surface, dict):
            continue
        candidate = str(surface.get("host_route_template") or "").strip()
        if candidate:
            return candidate
    if pack_meta.get("ui_components"):
        return f"/workspaces/{{workspaceId}}/capability-ui-hosts/{capability_code}"
    return None


def build_mobile_workbench_gateway_support_payload(
    capability_code: str,
    pack_meta: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_capability_code = str(
        pack_meta.get("code") or pack_meta.get("id") or capability_code
    ).strip()
    ui_components = [
        component
        for component in (pack_meta.get("ui_components", []) or [])
        if isinstance(component, dict)
    ]
    main_page_component_codes = [
        str(component.get("code") or "").strip()
        for component in ui_components
        if _is_main_page_component(component)
    ]
    api_prefixes = _normalize_string_list(
        [
            api.get("prefix")
            for api in (pack_meta.get("apis", []) or [])
            if isinstance(api, dict)
        ]
    )
    return {
        "capability_code": normalized_capability_code,
        "display_name": str(
            pack_meta.get("display_name")
            or pack_meta.get("name")
            or normalized_capability_code
        ),
        "supported": bool(ui_components),
        "has_ui_components": bool(ui_components),
        "host_route_template": _resolve_host_route_template(
            pack_meta, normalized_capability_code
        ),
        "main_page_component_codes": _normalize_string_list(main_page_component_codes),
        "api_prefixes": api_prefixes,
    }

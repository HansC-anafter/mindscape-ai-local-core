from typing import Any, Dict, List


_RESERVED_LEGACY_API_ROOTS = {
    "admin",
    "capability-packs",
    "deploy",
    "host",
    "host-resources",
    "host-runtime",
    "providers",
    "system-settings",
    "workspaces",
}
_REMOTE_REQUEST_SCOPE_CONTRACTS = {
    "explicit_workspace_v1",
    "no_remote_requests_v1",
}


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


def _normalize_workspace_route_templates(values: Any) -> List[str]:
    templates = _normalize_string_list(values)
    return [
        template
        for template in templates[:8]
        if template.startswith("/api/v1/workspaces/{workspaceId}/")
    ]


def _is_main_page_component(component: Dict[str, Any]) -> bool:
    code = str(component.get("code") or "").strip()
    if not code:
        return False
    return (
        code.endswith("Page")
        or code.endswith("StudioPage")
        or code.endswith("Workbench")
    )


def _is_owned_api_prefix(api_prefix: str, capability_code: str) -> bool:
    normalized = str(api_prefix or "").strip().rstrip("/")
    aliases = {capability_code, capability_code.replace("_", "-")}
    owned_roots = {
        f"/api/v1/capabilities/{alias}"
        for alias in aliases
    }
    if capability_code not in _RESERVED_LEGACY_API_ROOTS:
        owned_roots.update(
            f"/api/v1/{alias}"
            for alias in aliases
            if alias not in _RESERVED_LEGACY_API_ROOTS
        )
    return any(
        normalized == root or normalized.startswith(f"{root}/")
        for root in owned_roots
    )


def _canonical_host_route_template(capability_code: str) -> str:
    return f"/workspaces/{{workspaceId}}/capability-ui-hosts/{capability_code}"


def _resolve_host_route_template(
    pack_meta: Dict[str, Any],
    capability_code: str,
    main_page_component_codes: List[str],
) -> str | None:
    if not main_page_component_codes:
        return None
    canonical = _canonical_host_route_template(capability_code)
    explicit_templates = _normalize_string_list(
        [
            surface.get("host_route_template")
            for surface in (pack_meta.get("ui_surfaces", []) or [])
            if isinstance(surface, dict)
            and str(surface.get("host_route_template") or "").strip()
        ]
    )
    if explicit_templates and explicit_templates != [canonical]:
        return None
    return canonical


def build_mobile_workbench_gateway_support_payload(
    capability_code: str,
    pack_meta: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_capability_code = str(capability_code or "").strip().lower()
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
    declared_api_prefixes = _normalize_string_list(
        [
            api.get("prefix")
            for api in (pack_meta.get("apis", []) or [])
            if isinstance(api, dict)
        ]
    )
    api_prefixes_valid = all(
        _is_owned_api_prefix(prefix, normalized_capability_code)
        for prefix in declared_api_prefixes
    )
    normalized_main_page_component_codes = _normalize_string_list(
        main_page_component_codes
    )
    remote_workbench = pack_meta.get("remote_workbench")
    request_scope_contract = (
        str(remote_workbench.get("request_scope_contract") or "").strip()
        if isinstance(remote_workbench, dict)
        else ""
    )
    request_scope_valid = request_scope_contract in _REMOTE_REQUEST_SCOPE_CONTRACTS
    route_templates = _normalize_workspace_route_templates(
        remote_workbench.get("workspace_api_route_templates")
        if isinstance(remote_workbench, dict)
        else []
    )
    route_templates_valid = not isinstance(remote_workbench, dict) or (
        request_scope_contract == "no_remote_requests_v1" and not route_templates
    ) or bool(route_templates)
    # A legacy pack may declare the router mount ``/api/v1`` while its
    # remote contract names the exact workspace-scoped paths.  Never expose
    # that broad mount to a remote client; project only the validated route
    # templates in that case.
    if (
        declared_api_prefixes == ["/api/v1"]
        and route_templates_valid
        and route_templates
    ):
        api_prefixes = route_templates
        api_prefixes_valid = True
    else:
        api_prefixes = declared_api_prefixes if api_prefixes_valid else []
    remote_api_prefixes = (
        []
        if request_scope_contract == "no_remote_requests_v1"
        else api_prefixes
    )
    host_route_template = _resolve_host_route_template(
        pack_meta,
        normalized_capability_code,
        normalized_main_page_component_codes,
    )
    if not api_prefixes_valid or not request_scope_valid or not route_templates_valid:
        host_route_template = None
    supported = bool(ui_components) and bool(
        normalized_main_page_component_codes
    ) and host_route_template == _canonical_host_route_template(
        normalized_capability_code
    )
    return {
        "capability_code": normalized_capability_code,
        "display_name": str(
            pack_meta.get("display_name")
            or pack_meta.get("name")
            or normalized_capability_code
        ),
        "supported": supported,
        "has_ui_components": bool(ui_components),
        "host_route_template": host_route_template,
        "main_page_component_codes": normalized_main_page_component_codes,
        "api_prefixes": remote_api_prefixes,
        "request_scope_contract": request_scope_contract or None,
        "workspace_api_route_templates": route_templates,
    }

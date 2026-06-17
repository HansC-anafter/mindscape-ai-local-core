from typing import Any, Dict, Optional

from backend.app.models.tool_registry import RegisteredTool

_VALID_RISK_CLASSES = {"readonly", "soft_write", "external_write", "destructive"}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _planner_effect(tool_cfg: Dict[str, Any]) -> str:
    planner_contract = _as_dict(tool_cfg.get("planner_contract"))
    return str(planner_contract.get("effect") or "").strip().lower()


def _tool_cfg_read_only(tool_cfg: Dict[str, Any]) -> bool:
    if "read_only" in tool_cfg:
        return _coerce_bool(tool_cfg.get("read_only"))
    if _planner_effect(tool_cfg) == "read":
        return True
    if "side_effect_level" in tool_cfg:
        return str(tool_cfg.get("side_effect_level") or "").strip().lower() in {
            "none",
            "readonly",
        }
    return False


def _tool_cfg_side_effect_level(tool_cfg: Dict[str, Any], *, read_only: bool) -> str:
    explicit = str(tool_cfg.get("side_effect_level") or "").strip()
    if explicit:
        return explicit
    effect = _planner_effect(tool_cfg)
    if effect == "read":
        return "none"
    if effect == "write":
        return "soft_write"
    return "none" if read_only else "none"


def _tool_cfg_risk_class(
    tool_cfg: Dict[str, Any],
    *,
    read_only: bool,
    side_effect_level: str,
) -> str:
    explicit = str(tool_cfg.get("risk_class") or "").strip()
    if explicit in _VALID_RISK_CLASSES:
        return explicit
    normalized_side_effect = side_effect_level.strip().lower()
    if read_only or normalized_side_effect in {"none", "readonly"}:
        return "readonly"
    if normalized_side_effect == "soft_write":
        return "soft_write"
    if normalized_side_effect == "external_write":
        return "external_write"
    return "readonly"


def _manifest_tool_input_schema(tool_cfg: Dict[str, Any]) -> Dict[str, Any]:
    input_schema = tool_cfg.get("input_schema")
    return input_schema if isinstance(input_schema, dict) else {}


def _tool_cfg_from_tool_info_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    tool_info = _as_dict(metadata or {}).get("tool_info")
    if not isinstance(tool_info, dict):
        return {}
    nested = tool_info.get("tool_info")
    return nested if isinstance(nested, dict) else tool_info


def _registered_tool_from_manifest_tool(
    *,
    capability_code: str,
    tool_cfg: Dict[str, Any],
) -> Optional[RegisteredTool]:
    tool_code = tool_cfg.get("code") or tool_cfg.get("name")
    if not tool_code:
        return None
    tool_id = f"{capability_code}.{tool_code}"
    read_only = _tool_cfg_read_only(tool_cfg)
    side_effect_level = _tool_cfg_side_effect_level(tool_cfg, read_only=read_only)
    risk_class = _tool_cfg_risk_class(
        tool_cfg,
        read_only=read_only,
        side_effect_level=side_effect_level,
    )
    return RegisteredTool(
        tool_id=tool_id,
        site_id=capability_code,
        provider="capability",
        display_name=tool_cfg.get("display_name") or tool_code,
        origin_capability_id=tool_id,
        category=tool_cfg.get("category") or "capability",
        description=tool_cfg.get("description") or "",
        endpoint="",
        methods=[],
        danger_level=str(tool_cfg.get("danger_level") or "low"),
        input_schema=_manifest_tool_input_schema(tool_cfg),
        enabled=True,
        read_only=read_only,
        allowed_agent_roles=[],
        side_effect_level=side_effect_level,
        scope="system",
        capability_code=capability_code,
        risk_class=risk_class,
    )


def _registered_tool_from_capability_tool_info(tool_info: Any) -> RegisteredTool:
    tool_cfg = _tool_cfg_from_tool_info_metadata(getattr(tool_info, "metadata", None))
    tool_id = str(getattr(tool_info, "tool_id", "") or "")
    capability_code = (
        str(tool_id.split(".", 1)[0]).strip()
        if "." in tool_id
        else str(tool_cfg.get("capability") or "").strip()
    )
    capability_code = capability_code or "capability"
    read_only = _tool_cfg_read_only(tool_cfg)
    side_effect_level = _tool_cfg_side_effect_level(tool_cfg, read_only=read_only)
    risk_class = _tool_cfg_risk_class(
        tool_cfg,
        read_only=read_only,
        side_effect_level=side_effect_level,
    )
    return RegisteredTool(
        tool_id=tool_id,
        site_id="capability",
        provider="capability",
        display_name=getattr(tool_info, "name", None) or tool_id,
        origin_capability_id=tool_id,
        category=getattr(tool_info, "category", None) or "capability",
        description=getattr(tool_info, "description", None) or "",
        endpoint="",
        methods=[],
        danger_level=str(tool_cfg.get("danger_level") or "low"),
        input_schema=_manifest_tool_input_schema(tool_cfg),
        enabled=bool(getattr(tool_info, "enabled", True)),
        read_only=read_only,
        allowed_agent_roles=[],
        side_effect_level=side_effect_level,
        scope="system",
        capability_code=capability_code,
        risk_class=risk_class,
    )


def _tool_info_has_policy_metadata(tool_info: Any) -> bool:
    tool_cfg = _tool_cfg_from_tool_info_metadata(getattr(tool_info, "metadata", None))
    if not tool_cfg:
        return False
    if any(key in tool_cfg for key in ("read_only", "risk_class", "side_effect_level")):
        return True
    return _planner_effect(tool_cfg) in {"read", "write"}


def _overlay_registered_tool_policy_metadata(
    existing_tool: RegisteredTool,
    manifest_tool: RegisteredTool,
) -> None:
    existing_tool.read_only = manifest_tool.read_only
    existing_tool.side_effect_level = manifest_tool.side_effect_level
    existing_tool.risk_class = manifest_tool.risk_class
    if manifest_tool.capability_code:
        existing_tool.capability_code = manifest_tool.capability_code

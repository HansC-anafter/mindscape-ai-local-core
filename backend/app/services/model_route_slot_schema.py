"""
Model route slot schema and value helpers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

_ROUTE_DEPENDENCY_CODES = frozenset({"core_llm", "shared_llm"})
_ROUTE_SETTINGS_PANEL_SECTIONS = frozenset(
    {"model-routing", "runtime-environments", "workflow-engines"}
)
_SYSTEM_SETTING_SLOTS = (
    (
        "default_llm_provider",
        "Default LLM Provider",
        "llm_provider_default",
        "basic:models-and-quota",
    ),
    (
        "enable_capability_profile",
        "Governed Capability Profiles",
        "stage_profile_gate",
        "basic:models-and-quota",
    ),
    ("chat_model", "Chat Model", "chat_model_default", "basic:llm-chat"),
    (
        "embedding_model",
        "Embedding Model",
        "embedding_model_default",
        "basic:embedding",
    ),
    (
        "gemini_cli_auth_mode",
        "Gemini CLI Auth Mode",
        "runtime_auth_mode",
        "tab:runtime",
    ),
    (
        "agent_cli_model",
        "Gemini CLI Agent Model",
        "runtime_agent_model",
        "tab:runtime",
    ),
)


@dataclass
class ModelRouteSlot:
    slot_id: str
    owner_kind: str
    owner_id: str
    owner_name: str
    slot_kind: str
    title: str
    summary: str
    route_family: str
    source: str
    settings_anchor: str = "basic:model-routing-registry"
    installed: Optional[bool] = None
    enabled: Optional[bool] = None
    evidence_path: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["raw"] = dict(self.raw or {})
        return payload


def summarize_model_route_value(value: Any) -> str:
    if isinstance(value, dict):
        parts = [f"{key}->{item}" for key, item in list(value.items())[:6]]
        return ", ".join(parts)
    if isinstance(value, list):
        preview = [str(item) for item in value[:6]]
        suffix = "..." if len(value) > 6 else ""
        return ", ".join(preview) + suffix
    return str(value)


def summarize_model_route_mapping(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, entry in value.items():
            if isinstance(entry, (dict, list)):
                parts.append(f"{key}={summarize_model_route_value(entry)}")
            else:
                parts.append(f"{key}={entry}")
        return ", ".join(parts[:6])
    return summarize_model_route_value(value)


def slug_model_route_value(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "slot"
    slug = "".join(ch if ch.isalnum() else "_" for ch in text)
    slug = "_".join(part for part in slug.split("_") if part)
    return slug or "slot"


def build_model_route_slot(
    *,
    pack_id: str,
    owner_name: str,
    slot_kind: str,
    title: str,
    summary: str,
    route_family: str,
    source: str,
    evidence_path: Optional[str],
    installed: Optional[bool],
    enabled: Optional[bool],
    raw: Optional[Dict[str, Any]] = None,
    owner_kind: str = "pack",
    settings_anchor: str = "basic:model-routing-registry",
) -> ModelRouteSlot:
    return ModelRouteSlot(
        slot_id=f"{pack_id}:{slug_model_route_value(slot_kind)}:{slug_model_route_value(title)}",
        owner_kind=owner_kind,
        owner_id=pack_id,
        owner_name=owner_name,
        slot_kind=slot_kind,
        title=title,
        summary=summary,
        route_family=route_family,
        source=source,
        settings_anchor=settings_anchor,
        installed=installed,
        enabled=enabled,
        evidence_path=str(evidence_path) if evidence_path else None,
        raw=dict(raw or {}),
    )

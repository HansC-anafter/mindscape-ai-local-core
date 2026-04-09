"""
Pack-owned ComfyUI runtime configuration helpers.

The source of truth for ComfyUI-specific runtime path semantics lives in the
`comfyui_runtime` capability pack. The pack may depend on local-core generic
host primitives such as the system settings store, but the capability-specific
resolution logic should not live in `local-core/services`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional

from backend.app.models.system_settings import SettingType, SystemSetting
from capabilities.comfyui_runtime.services.talking_head_backend_catalog import (
    DEFAULT_TALKING_HEAD_BACKEND_PRESET,
    get_talking_head_backend_preset,
)

if TYPE_CHECKING:
    from backend.app.services.system_settings_store import SystemSettingsStore


SETTING_KEY = "comfyui_preview_runtime"

STRING_FIELDS = (
    "install_path",
    "main_py",
    "python_bin",
    "log_file",
    "extra_model_paths_config",
    "health_host",
    "listen",
    "talking_head_backend_preset",
    "talking_head_backend_repo",
    "talking_head_backend_family",
    "talking_head_backend_ref",
    "talking_head_backend_dir",
    "talking_head_viseme_bridge_repo",
    "talking_head_viseme_bridge_ref",
    "talking_head_viseme_bridge_dir",
)


def derive_runtime_paths_from_install_path(install_path: str) -> Dict[str, str]:
    normalized = str(install_path or "").strip().rstrip("/")
    if not normalized:
        return {
            "main_py": "",
            "python_bin": "",
            "log_file": "",
            "extra_model_paths_config": "",
        }

    return {
        "main_py": os.path.join(normalized, "main.py"),
        "python_bin": os.path.join(normalized, ".venv", "bin", "python"),
        "log_file": os.path.join(normalized, "comfyui_server.log"),
        "extra_model_paths_config": os.path.join(
            normalized, "extra_model_paths.yaml"
        ),
    }


def derive_talking_head_paths_from_install_path(install_path: str) -> Dict[str, str]:
    normalized = str(install_path or "").strip().rstrip("/")
    if not normalized:
        return {
            "talking_head_backend_dir": "",
            "talking_head_viseme_bridge_dir": "",
        }

    return {
        "talking_head_backend_dir": os.path.join(
            normalized,
            "custom_nodes",
            "mindscape_liveportrait_audio_runtime",
        ),
        "talking_head_viseme_bridge_dir": os.path.join(
            normalized,
            "custom_nodes",
            "mindscape_viseme_alignment_bridge",
        ),
    }


def _clean_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_port(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def build_talking_head_source_install_summary(
    *,
    effective_config: Mapping[str, Any],
    preset_meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    preset_id = (
        _clean_string(effective_config.get("talking_head_backend_preset"))
        or DEFAULT_TALKING_HEAD_BACKEND_PRESET
    )
    preset = dict(preset_meta or get_talking_head_backend_preset(preset_id))
    source_map = dict(effective_config.get("source_map") or {})
    backend_family = (
        _clean_string(effective_config.get("talking_head_backend_family"))
        or _clean_string(preset.get("backend_family"))
        or "liveportrait_style_audio_driven_custom_nodes"
    )
    backend_repo = _clean_string(effective_config.get("talking_head_backend_repo")) or ""
    viseme_repo = (
        _clean_string(effective_config.get("talking_head_viseme_bridge_repo")) or ""
    )
    supports_auto_install = bool(preset.get("supports_auto_install"))
    blockers: list[str] = []

    if backend_family == "manual_existing_nodes":
        configuration_state = "manual_only"
    else:
        if not supports_auto_install:
            blockers.append("preset_manual_only")
        if not backend_repo:
            blockers.append("backend_repo_unset")
        if not viseme_repo:
            blockers.append("viseme_bridge_repo_unset")
        configuration_state = (
            "actionable_source_install" if not blockers else "blocked_configuration"
        )

    return {
        "preset_id": preset_id,
        "backend_family": backend_family,
        "supports_auto_install": supports_auto_install,
        "backend_contract_verification_mode": _clean_string(
            preset.get("contract_verification_mode")
        )
        or "preset_declared",
        "declared_runtime_install_specs": list(
            preset.get("declared_runtime_install_specs") or []
        ),
        "declared_node_classes": list(
            preset.get("declared_node_classes") or []
        ),
        "default_backend_repo": _clean_string(preset.get("default_backend_repo")) or "",
        "default_backend_ref": _clean_string(preset.get("default_backend_ref")) or "main",
        "default_viseme_bridge_repo": _clean_string(preset.get("default_viseme_repo")) or "",
        "default_viseme_bridge_ref": _clean_string(preset.get("default_viseme_ref")) or "main",
        "resolved_backend_repo": backend_repo,
        "resolved_backend_repo_source": source_map.get(
            "talking_head_backend_repo", "unset"
        ),
        "resolved_viseme_bridge_repo": viseme_repo,
        "resolved_viseme_bridge_repo_source": source_map.get(
            "talking_head_viseme_bridge_repo", "unset"
        ),
        "resolved_backend_dir": _clean_string(
            effective_config.get("talking_head_backend_dir")
        )
        or "",
        "resolved_viseme_bridge_dir": _clean_string(
            effective_config.get("talking_head_viseme_bridge_dir")
        )
        or "",
        "configuration_state": configuration_state,
        "configuration_blockers": blockers,
    }


class ComfyUIPreviewRuntimeConfigService:
    def __init__(
        self,
        settings_store: Optional["SystemSettingsStore"] = None,
        environ: Optional[Mapping[str, str]] = None,
    ) -> None:
        if settings_store is None:
            from backend.app.services.system_settings_store import SystemSettingsStore

            settings_store = SystemSettingsStore()
        self.settings_store = settings_store
        self.environ = environ or os.environ

    def get_stored_config(self) -> Dict[str, Any]:
        setting = self.settings_store.get_setting(SETTING_KEY)
        raw = setting.value if setting and isinstance(setting.value, dict) else {}
        return self._normalize_payload(raw)

    def clear_config(self) -> Dict[str, Any]:
        setting = SystemSetting(
            key=SETTING_KEY,
            value={},
            value_type=SettingType.JSON,
            category="runtime",
            description="ComfyUI preview runtime configuration",
            is_sensitive=False,
            is_user_editable=True,
            default_value={},
        )
        self.settings_store.save_setting(setting)
        return {}

    def update_config(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        merged = dict(self.get_stored_config())

        for field in STRING_FIELDS:
            if field not in payload:
                continue
            value = _clean_string(payload.get(field))
            if value is None:
                merged.pop(field, None)
            else:
                merged[field] = value

        if "port" in payload:
            port = _clean_port(payload.get("port"))
            if port is None:
                merged.pop("port", None)
            else:
                merged["port"] = port

        setting = SystemSetting(
            key=SETTING_KEY,
            value=merged,
            value_type=SettingType.JSON,
            category="runtime",
            description="ComfyUI preview runtime configuration",
            is_sensitive=False,
            is_user_editable=True,
            default_value={},
            metadata={
                "schema_version": 1,
                "runtime_type": "comfyui",
                "capability_code": "comfyui_runtime",
            },
        )
        self.settings_store.save_setting(setting)
        return merged

    def get_effective_config(self) -> Dict[str, Any]:
        stored = self.get_stored_config()
        source_map: Dict[str, str] = {}

        install_path = _clean_string(stored.get("install_path"))
        if install_path:
            source_map["install_path"] = "user_setting"
        else:
            install_path = self._resolve_env_string("COMFYUI_BASE_DIR")
            if install_path:
                source_map["install_path"] = "env:COMFYUI_BASE_DIR"
            else:
                install_path = ""
                source_map["install_path"] = "unset"

        derived_from_install = derive_runtime_paths_from_install_path(install_path)
        derived_talking_head_paths = derive_talking_head_paths_from_install_path(
            install_path
        )

        main_py = _clean_string(stored.get("main_py"))
        if main_py:
            source_map["main_py"] = "user_setting"
        else:
            candidate = derived_from_install["main_py"]
            if candidate:
                main_py = candidate
                source_map["main_py"] = "derived_from_install_path"
            else:
                main_py = self._resolve_env_string("COMFYUI_MAIN_PY") or ""
                source_map["main_py"] = (
                    "env:COMFYUI_MAIN_PY" if main_py else "unset"
                )

        python_bin = _clean_string(stored.get("python_bin"))
        if python_bin:
            source_map["python_bin"] = "user_setting"
        else:
            python_bin = self._resolve_env_string("COMFYUI_PYTHON_BIN")
            if python_bin:
                source_map["python_bin"] = "env:COMFYUI_PYTHON_BIN"
            elif derived_from_install["python_bin"]:
                python_bin = derived_from_install["python_bin"]
                source_map["python_bin"] = "derived_from_install_path"
            else:
                python_bin = ""
                source_map["python_bin"] = "unset"

        log_file = _clean_string(stored.get("log_file"))
        if log_file:
            source_map["log_file"] = "user_setting"
        else:
            log_file = self._resolve_env_string("COMFYUI_LOG_FILE")
            if log_file:
                source_map["log_file"] = "env:COMFYUI_LOG_FILE"
            elif derived_from_install["log_file"]:
                log_file = derived_from_install["log_file"]
                source_map["log_file"] = "derived_from_install_path"
            else:
                log_file = ""
                source_map["log_file"] = "unset"

        extra_model_paths_config = _clean_string(stored.get("extra_model_paths_config"))
        if extra_model_paths_config:
            source_map["extra_model_paths_config"] = "user_setting"
        else:
            extra_model_paths_config = self._resolve_env_string(
                "COMFYUI_EXTRA_MODEL_PATHS_CONFIG"
            )
            if extra_model_paths_config:
                source_map["extra_model_paths_config"] = "env:COMFYUI_EXTRA_MODEL_PATHS_CONFIG"
            elif derived_from_install["extra_model_paths_config"]:
                extra_model_paths_config = derived_from_install[
                    "extra_model_paths_config"
                ]
                source_map["extra_model_paths_config"] = "derived_from_install_path"
            else:
                extra_model_paths_config = ""
                source_map["extra_model_paths_config"] = "unset"

        health_host = self._resolve_string_or_default(
            stored=stored.get("health_host"),
            env_key="COMFYUI_HEALTH_HOST",
            fallback="127.0.0.1",
            source_map=source_map,
            target_key="health_host",
        )
        listen = self._resolve_string_or_default(
            stored=stored.get("listen"),
            env_key="COMFYUI_LISTEN",
            fallback="0.0.0.0",
            source_map=source_map,
            target_key="listen",
        )

        port = _clean_port(stored.get("port"))
        if port is not None:
            source_map["port"] = "user_setting"
        else:
            port = _clean_port(self.environ.get("COMFYUI_PORT"))
            if port is not None:
                source_map["port"] = "env:COMFYUI_PORT"
            else:
                port = 8188
                source_map["port"] = "default"

        talking_head_backend_preset = self._resolve_string_or_default(
            stored=stored.get("talking_head_backend_preset"),
            env_key="MINDSCAPE_TALKING_HEAD_BACKEND_PRESET",
            fallback=DEFAULT_TALKING_HEAD_BACKEND_PRESET,
            source_map=source_map,
            target_key="talking_head_backend_preset",
        )
        talking_head_preset = get_talking_head_backend_preset(
            talking_head_backend_preset,
            environ=self.environ,
        )
        talking_head_backend_repo = self._resolve_optional_string(
            stored=stored.get("talking_head_backend_repo"),
            env_key="MINDSCAPE_TALKING_HEAD_BACKEND_REPO",
            source_map=source_map,
            target_key="talking_head_backend_repo",
            fallback=_clean_string(talking_head_preset.get("default_backend_repo")),
            fallback_source=f"preset:{talking_head_backend_preset}",
        )
        talking_head_backend_family = self._resolve_string_or_default(
            stored=stored.get("talking_head_backend_family"),
            env_key="MINDSCAPE_TALKING_HEAD_BACKEND_FAMILY",
            fallback=_clean_string(talking_head_preset.get("backend_family"))
            or "liveportrait_style_audio_driven_custom_nodes",
            source_map=source_map,
            target_key="talking_head_backend_family",
        )
        talking_head_backend_ref = self._resolve_string_or_default(
            stored=stored.get("talking_head_backend_ref"),
            env_key="MINDSCAPE_TALKING_HEAD_BACKEND_REF",
            fallback=_clean_string(talking_head_preset.get("default_backend_ref"))
            or "main",
            source_map=source_map,
            target_key="talking_head_backend_ref",
        )
        talking_head_backend_dir = self._resolve_path_override(
            stored=stored.get("talking_head_backend_dir"),
            env_key="MINDSCAPE_TALKING_HEAD_BACKEND_DIR",
            derived_value=derived_talking_head_paths["talking_head_backend_dir"],
            source_map=source_map,
            target_key="talking_head_backend_dir",
        )
        talking_head_viseme_bridge_repo = self._resolve_optional_string(
            stored=stored.get("talking_head_viseme_bridge_repo"),
            env_key="MINDSCAPE_TALKING_HEAD_VISEME_BRIDGE_REPO",
            source_map=source_map,
            target_key="talking_head_viseme_bridge_repo",
            fallback=_clean_string(talking_head_preset.get("default_viseme_repo")),
            fallback_source=f"preset:{talking_head_backend_preset}",
        )
        talking_head_viseme_bridge_ref = self._resolve_string_or_default(
            stored=stored.get("talking_head_viseme_bridge_ref"),
            env_key="MINDSCAPE_TALKING_HEAD_VISEME_BRIDGE_REF",
            fallback=_clean_string(talking_head_preset.get("default_viseme_ref"))
            or "main",
            source_map=source_map,
            target_key="talking_head_viseme_bridge_ref",
        )
        talking_head_viseme_bridge_dir = self._resolve_path_override(
            stored=stored.get("talking_head_viseme_bridge_dir"),
            env_key="MINDSCAPE_TALKING_HEAD_VISEME_BRIDGE_DIR",
            derived_value=derived_talking_head_paths["talking_head_viseme_bridge_dir"],
            source_map=source_map,
            target_key="talking_head_viseme_bridge_dir",
        )

        effective_config = {
            "install_path": install_path,
            "main_py": main_py,
            "python_bin": python_bin,
            "log_file": log_file,
            "extra_model_paths_config": extra_model_paths_config,
            "health_host": health_host,
            "listen": listen,
            "port": port,
            "talking_head_backend_preset": talking_head_backend_preset,
            "talking_head_backend_repo": talking_head_backend_repo or "",
            "talking_head_backend_family": talking_head_backend_family,
            "talking_head_backend_ref": talking_head_backend_ref,
            "talking_head_backend_dir": talking_head_backend_dir,
            "talking_head_viseme_bridge_repo": talking_head_viseme_bridge_repo or "",
            "talking_head_viseme_bridge_ref": talking_head_viseme_bridge_ref,
            "talking_head_viseme_bridge_dir": talking_head_viseme_bridge_dir,
            "health_url": f"http://{health_host}:{port}/system_stats",
            "install_path_configured": bool(_clean_string(stored.get("install_path"))),
            "stored_overrides": stored,
            "source_map": source_map,
        }
        effective_config["talking_head_source_install"] = (
            build_talking_head_source_install_summary(
                effective_config=effective_config,
                preset_meta=talking_head_preset,
            )
        )
        return effective_config

    def _normalize_payload(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for field in STRING_FIELDS:
            value = _clean_string(payload.get(field))
            if value is not None:
                normalized[field] = value
        port = _clean_port(payload.get("port"))
        if port is not None:
            normalized["port"] = port
        return normalized

    def _resolve_env_string(self, env_key: str) -> Optional[str]:
        return _clean_string(self.environ.get(env_key))

    def _resolve_optional_string(
        self,
        *,
        stored: Any,
        env_key: str,
        source_map: Dict[str, str],
        target_key: str,
        fallback: Optional[str] = None,
        fallback_source: str = "unset",
    ) -> Optional[str]:
        value = _clean_string(stored)
        if value is not None:
            source_map[target_key] = "user_setting"
            return value
        env_value = self._resolve_env_string(env_key)
        if env_value is not None:
            source_map[target_key] = f"env:{env_key}"
            return env_value
        preset_value = _clean_string(fallback)
        if preset_value is not None:
            source_map[target_key] = fallback_source
            return preset_value
        source_map[target_key] = "unset"
        return None

    def _resolve_path_override(
        self,
        *,
        stored: Any,
        env_key: str,
        derived_value: str,
        source_map: Dict[str, str],
        target_key: str,
    ) -> str:
        value = _clean_string(stored)
        if value is not None:
            source_map[target_key] = "user_setting"
            return value
        env_value = self._resolve_env_string(env_key)
        if env_value is not None:
            source_map[target_key] = f"env:{env_key}"
            return env_value
        if derived_value:
            source_map[target_key] = "derived_from_install_path"
            return derived_value
        source_map[target_key] = "unset"
        return ""

    def _resolve_string_or_default(
        self,
        *,
        stored: Any,
        env_key: str,
        fallback: str,
        source_map: Dict[str, str],
        target_key: str,
        fallback_source: str = "default",
    ) -> str:
        value = _clean_string(stored)
        if value is not None:
            source_map[target_key] = "user_setting"
            return value
        env_value = self._resolve_env_string(env_key)
        if env_value is not None:
            source_map[target_key] = f"env:{env_key}"
            return env_value
        source_map[target_key] = fallback_source
        return fallback

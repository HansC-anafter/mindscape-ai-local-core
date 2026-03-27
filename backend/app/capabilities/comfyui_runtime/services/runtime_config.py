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

        return {
            "install_path": install_path,
            "main_py": main_py,
            "python_bin": python_bin,
            "log_file": log_file,
            "extra_model_paths_config": extra_model_paths_config,
            "health_host": health_host,
            "listen": listen,
            "port": port,
            "health_url": f"http://{health_host}:{port}/system_stats",
            "install_path_configured": bool(_clean_string(stored.get("install_path"))),
            "stored_overrides": stored,
            "source_map": source_map,
        }

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

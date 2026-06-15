"""Default setting initialization for SystemSettingsStore."""

import logging

from backend.app.models.system_settings import SystemSetting, SettingType

logger = logging.getLogger(__name__)


class SystemSettingsDefaultsMixin:
    def _init_default_settings(self):
        """Initialize default system settings"""
        default_settings = [
            {
                "key": "default_language",
                "value": "zh-TW",
                "value_type": SettingType.STRING,
                "category": "ui",
                "description": "Default UI language",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "zh-TW",
            },
            {
                "key": "default_llm_provider",
                "value": "openai",
                "value_type": SettingType.STRING,
                "category": "llm",
                "description": "Default LLM provider (openai, anthropic, etc.)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "openai",
            },
            {
                "key": "enable_capability_profile",
                "value": "true",
                "value_type": SettingType.BOOLEAN,
                "category": "llm",
                "description": "Enable capability profile system for staged model switching (default: true)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "true",
            },
            {
                "key": "chat_model",
                "value": "gpt-5.4",
                "value_type": SettingType.STRING,
                "category": "llm",
                "description": "Model for chat/conversation inference (latest: gpt-5.1, gpt-5.1-pro, claude-haiku-4.5)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "gpt-5.4",
                "metadata": {
                    "provider": "openai",
                    "model_type": "chat",
                    "is_latest": True,
                },
            },
            {
                "key": "embedding_model",
                "value": "text-embedding-3-large",
                "value_type": SettingType.STRING,
                "category": "llm",
                "description": "Model for embeddings/vectorization (latest: text-embedding-3-large, supports adjustable dimensions)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "text-embedding-3-large",
                "metadata": {
                    "provider": "openai",
                    "model_type": "embedding",
                    "is_latest": True,
                    "dimensions": 3072,
                },
            },
            {
                "key": "enable_analytics",
                "value": False,
                "value_type": SettingType.BOOLEAN,
                "category": "general",
                "description": "Enable usage analytics",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": False,
            },
            {
                "key": "auto_save_enabled",
                "value": True,
                "value_type": SettingType.BOOLEAN,
                "category": "ui",
                "description": "Enable auto-save for workspaces",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": True,
            },
            # Cloud Extension Settings (Neutral - all providers configured here)
            {
                "key": "cloud_providers",
                "value": [],
                "value_type": SettingType.JSON,
                "category": "cloud",
                "description": "List of cloud playbook providers (all providers, including official, are configured here)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": [],
                "metadata": {
                    "schema": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "provider_id": {"type": "string"},
                                "provider_type": {
                                    "type": "string",
                                    "enum": ["official", "generic_http", "custom"],
                                },
                                "enabled": {"type": "boolean"},
                                "config": {"type": "object"},
                            },
                            "required": [
                                "provider_id",
                                "provider_type",
                                "enabled",
                                "config",
                            ],
                        },
                    }
                },
            },
            # Google OAuth Settings
            {
                "key": "google_oauth_client_id",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth 2.0 Client ID for Google Drive integration",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "google_oauth_client_secret",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth 2.0 Client Secret for Google Drive integration",
                "is_sensitive": True,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "google_oauth_redirect_uri",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth Redirect URI (default: auto-generated from BACKEND_URL)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "backend_url",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Backend URL for OAuth callback construction",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
            # Gemini CLI Auth Settings
            {
                "key": "gemini_cli_auth_mode",
                "value": "gemini_api_key",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "Auth mode for Gemini CLI (gca, gemini_api_key, or vertex_ai)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "gemini_api_key",
                "metadata": {
                    "allowed_values": ["gca", "gemini_api_key", "vertex_ai"],
                },
            },
            {
                "key": "agent_cli_model",
                "value": "gemini-3-pro",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "Model for Gemini CLI agent execution (e.g. gemini-3-pro, gemini-3-flash, gemini-2.5-pro)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "gemini-3-pro",
                "metadata": {
                    "allowed_values": [
                        "gemini-3-pro",
                        "gemini-3-flash",
                        "gemini-2.5-pro",
                        "gemini-2.5-flash",
                    ],
                },
            },
            {
                "key": "gemini_api_key",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "Google AI Studio API key for Gemini CLI (aistudio.google.com/apikey)",
                "is_sensitive": True,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "google_cloud_project",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "GCP project ID for Vertex AI auth mode",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "google_cloud_location",
                "value": "us-central1",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "GCP location for Vertex AI auth mode",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "us-central1",
            },
            {
                "key": "gca_oauth_client_id",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "GCA OAuth Client ID for Gemini CLI (installed application type, from open-source gemini-cli)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "gca_oauth_client_secret",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "GCA OAuth Client Secret for Gemini CLI (installed application, not confidential by design)",
                "is_sensitive": True,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "gca_oauth_scopes",
                "value": "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "OAuth scopes required by cloudcode-pa.googleapis.com (space-separated)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile",
            },
            {
                "key": "claude_api_key",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "Anthropic API key for Claude Code CLI (console.anthropic.com/settings/keys)",
                "is_sensitive": True,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "openai_api_key",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "gemini_cli",
                "description": "OpenAI API key for Codex CLI (platform.openai.com/api-keys)",
                "is_sensitive": True,
                "is_user_editable": True,
                "default_value": "",
            },
        ]

        for setting_data in default_settings:
            try:
                existing = self.get_setting(setting_data["key"])
                if not existing:
                    setting = SystemSetting(**setting_data)
                    self.save_setting(setting)
            except Exception as exc:
                logger.warning(
                    "Failed to initialize default setting %s: %s",
                    setting_data["key"],
                    exc,
                )

    def _migrate_settings(self):
        """Migrate existing settings to ensure compatibility"""
        try:
            enable_flag = self.get_setting("enable_capability_profile")
            if not enable_flag or str(enable_flag.value).lower() not in ["true", "1"]:
                logger.info(
                    "Migrating enable_capability_profile: setting to True (default)"
                )
                self.set_setting(
                    key="enable_capability_profile",
                    value=True,
                    value_type=SettingType.BOOLEAN,
                    category="llm",
                    description=(
                        "Enable capability profile system for staged model switching (default: true)"
                    ),
                    is_user_editable=True,
                )
        except Exception as exc:
            logger.warning("Failed to migrate settings: %s", exc, exc_info=True)

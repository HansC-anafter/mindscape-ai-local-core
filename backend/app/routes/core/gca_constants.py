"""
GCA (Google Code Assist) OAuth Constants

Reads GCA OAuth credentials from SystemSettingsStore (database).
Users can configure these through the web console settings page.

Originally from Gemini CLI's open-source codebase (Apache 2.0),
these are "installed application" type credentials where client_secret
is not confidential by design. Stored in system_settings so users
can update them without code changes.
"""

import logging

logger = logging.getLogger(__name__)

# Default scopes (not a secret, safe to keep here)
GCA_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

GCA_OAUTH_SCOPES_STRING = " ".join(GCA_OAUTH_SCOPES)


def _get_setting(key: str) -> str:
    """Read a setting from SystemSettingsStore with lazy import."""
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        store = SystemSettingsStore()
        setting = store.get_setting(key)
        if setting and setting.value:
            return str(setting.value)
    except Exception as e:
        logger.warning("Failed to read %s from settings: %s", key, e)
    return ""


def get_gca_client_id() -> str:
    """Read GCA OAuth Client ID from system settings."""
    return _get_setting("gca_oauth_client_id")


def get_gca_client_secret() -> str:
    """Read GCA OAuth Client Secret from system settings."""
    return _get_setting("gca_oauth_client_secret")

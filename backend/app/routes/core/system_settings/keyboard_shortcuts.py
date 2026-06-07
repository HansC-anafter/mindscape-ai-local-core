"""
Keyboard shortcut preference endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import Field

from backend.app.services.keyboard_shortcut_catalog import (
    build_keyboard_shortcut_catalog,
)
from backend.app.services.keyboard_shortcut_profile import (
    KEYBOARD_SHORTCUTS_SCHEMA_VERSION,
    KEYBOARD_SHORTCUTS_SETTING_KEY,
    KeyboardShortcutProfile,
    build_keyboard_shortcut_setting,
)

from .shared import settings_store

router = APIRouter()


class KeyboardShortcutProfileResponse(KeyboardShortcutProfile):
    """Shortcut profile plus the installed command catalog."""

    updated_at: Optional[datetime] = None
    catalog: List[Dict[str, Any]] = Field(default_factory=list)


def _empty_response() -> KeyboardShortcutProfileResponse:
    return KeyboardShortcutProfileResponse(
        schema_version=KEYBOARD_SHORTCUTS_SCHEMA_VERSION,
        bindings=[],
        updated_at=None,
        catalog=build_keyboard_shortcut_catalog(),
    )


@router.get("/keyboard-shortcuts", response_model=KeyboardShortcutProfileResponse)
async def get_keyboard_shortcuts() -> KeyboardShortcutProfileResponse:
    """Get the persisted keyboard shortcut profile."""
    setting = settings_store.get_setting(KEYBOARD_SHORTCUTS_SETTING_KEY)
    if setting is None:
        return _empty_response()

    if not isinstance(setting.value, dict):
        raise HTTPException(
            status_code=500,
            detail="Stored keyboard shortcut profile must be a JSON object",
        )

    try:
        profile = KeyboardShortcutProfile.model_validate(setting.value)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Stored keyboard shortcut profile is invalid: {exc}",
        ) from exc

    return KeyboardShortcutProfileResponse(
        schema_version=profile.schema_version,
        bindings=profile.bindings,
        updated_at=setting.updated_at,
        catalog=build_keyboard_shortcut_catalog(),
    )


@router.put("/keyboard-shortcuts", response_model=KeyboardShortcutProfileResponse)
async def put_keyboard_shortcuts(
    profile: KeyboardShortcutProfile,
) -> KeyboardShortcutProfileResponse:
    """Persist the complete keyboard shortcut profile."""
    setting = build_keyboard_shortcut_setting(profile)
    updated = settings_store.save_setting(setting)
    return KeyboardShortcutProfileResponse(
        schema_version=profile.schema_version,
        bindings=profile.bindings,
        updated_at=updated.updated_at,
        catalog=build_keyboard_shortcut_catalog(),
    )

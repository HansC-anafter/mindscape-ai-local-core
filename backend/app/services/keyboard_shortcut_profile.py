"""
Keyboard shortcut profile models and validation.
"""

import re
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.models.system_settings import SettingType, SystemSetting

KEYBOARD_SHORTCUTS_CATEGORY = "keyboard_shortcuts"
KEYBOARD_SHORTCUTS_SETTING_KEY = "keyboard_shortcuts.bindings.v1"
KEYBOARD_SHORTCUTS_SCHEMA_VERSION = 1
MAX_BINDINGS = 500

_MODIFIER_ALIASES = {
    "shift": "Shift",
    "alt": "Alt",
    "option": "Alt",
    "ctrl": "Control",
    "control": "Control",
    "meta": "Meta",
    "cmd": "Meta",
    "command": "Meta",
    "mod": "Mod",
}
_VALID_KEY_TOKEN_PATTERN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_-]*|[,./;'`\[\]\\=-])$"
)


class KeyboardShortcutBinding(BaseModel):
    """A persisted shortcut override."""

    binding_id: str = Field(..., min_length=1, max_length=160)
    command_id: str = Field(..., min_length=1, max_length=120)
    owner_type: Literal["core", "pack"]
    owner_id: Optional[str] = Field(default=None, max_length=120)
    shortcut: Optional[str] = Field(default=None, max_length=80)
    disabled: bool = False

    @field_validator("binding_id", "command_id", "owner_id", mode="before")
    @classmethod
    def _strip_optional_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("shortcut")
    @classmethod
    def _validate_shortcut(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("shortcut must be null or a non-empty string")
        validate_shortcut_syntax(normalized)
        return normalized

    @model_validator(mode="after")
    def _validate_enabled_binding(self) -> "KeyboardShortcutBinding":
        if not self.disabled and self.shortcut == "":
            raise ValueError("enabled shortcut binding cannot use an empty shortcut")
        return self


class KeyboardShortcutProfile(BaseModel):
    """Persisted shortcut profile."""

    schema_version: Literal[1] = KEYBOARD_SHORTCUTS_SCHEMA_VERSION
    bindings: List[KeyboardShortcutBinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_profile(self) -> "KeyboardShortcutProfile":
        if len(self.bindings) > MAX_BINDINGS:
            raise ValueError(f"bindings cannot exceed {MAX_BINDINGS}")
        seen = set()
        for binding in self.bindings:
            if binding.binding_id in seen:
                raise ValueError(f"duplicate binding_id: {binding.binding_id}")
            seen.add(binding.binding_id)
        return self


def validate_shortcut_syntax(shortcut: str) -> None:
    """
    Validate the phase-one shortcut syntax.

    Args:
        shortcut: Shortcut string to validate
    """
    if shortcut.strip() != shortcut or re.search(r"\s", shortcut):
        raise ValueError("shortcut sequences and whitespace are not supported")

    parts = [part.strip() for part in shortcut.split("+") if part.strip()]
    if not parts:
        raise ValueError("shortcut must include a key")

    key = parts[-1]
    modifier_parts = parts[:-1]
    seen_modifiers = set()
    for modifier in modifier_parts:
        canonical = _MODIFIER_ALIASES.get(modifier.lower())
        if canonical is None:
            raise ValueError(f"invalid shortcut modifier: {modifier}")
        if canonical in seen_modifiers:
            raise ValueError(f"duplicate shortcut modifier: {modifier}")
        seen_modifiers.add(canonical)

    if key.lower() in _MODIFIER_ALIASES:
        raise ValueError("shortcut must include a non-modifier key")
    if not _VALID_KEY_TOKEN_PATTERN.match(key):
        raise ValueError(f"invalid shortcut key: {key}")


def build_keyboard_shortcut_setting(
    profile: KeyboardShortcutProfile,
) -> SystemSetting:
    """
    Build the system_settings row for a shortcut profile.

    Args:
        profile: Validated shortcut profile

    Returns:
        SystemSetting ready for persistence
    """
    return SystemSetting(
        key=KEYBOARD_SHORTCUTS_SETTING_KEY,
        value=profile.model_dump(mode="json"),
        value_type=SettingType.JSON,
        category=KEYBOARD_SHORTCUTS_CATEGORY,
        description="User keyboard shortcut overrides",
        is_sensitive=False,
        is_user_editable=True,
        default_value={
            "schema_version": KEYBOARD_SHORTCUTS_SCHEMA_VERSION,
            "bindings": [],
        },
        metadata={
            "schema_version": KEYBOARD_SHORTCUTS_SCHEMA_VERSION,
            "max_bindings": MAX_BINDINGS,
        },
    )

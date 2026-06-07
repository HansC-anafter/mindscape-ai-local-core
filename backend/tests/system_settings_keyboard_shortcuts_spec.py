import pytest

from pydantic import ValidationError

from backend.app.models.system_settings import SettingType
from backend.app.services.keyboard_shortcut_profile import (
    KEYBOARD_SHORTCUTS_SETTING_KEY,
    KeyboardShortcutProfile,
    build_keyboard_shortcut_setting,
)


def _profile_payload(shortcut="F9"):
    return {
        "schema_version": 1,
        "bindings": [
            {
                "binding_id": "workspace_tool:ig:feed_grid_card_load_limit:open",
                "command_id": "pack.workspace_tool.open",
                "owner_type": "pack",
                "owner_id": "ig",
                "shortcut": shortcut,
                "disabled": False,
            }
        ],
    }


def test_keyboard_shortcut_profile_accepts_pack_binding():
    profile = KeyboardShortcutProfile.model_validate(_profile_payload())

    assert profile.schema_version == 1
    assert profile.bindings[0].shortcut == "F9"


def test_keyboard_shortcut_setting_uses_json_system_setting():
    profile = KeyboardShortcutProfile.model_validate(_profile_payload("Shift+S"))

    setting = build_keyboard_shortcut_setting(profile)

    assert setting.key == KEYBOARD_SHORTCUTS_SETTING_KEY
    assert setting.category == "keyboard_shortcuts"
    assert setting.value_type == SettingType.JSON
    assert setting.value["bindings"][0]["shortcut"] == "Shift+S"


def test_keyboard_shortcut_profile_rejects_pure_modifier():
    with pytest.raises(ValidationError):
        KeyboardShortcutProfile.model_validate(_profile_payload("Shift"))


def test_keyboard_shortcut_profile_rejects_duplicate_binding_ids():
    payload = _profile_payload()
    payload["bindings"].append(
        {
            **payload["bindings"][0],
            "shortcut": "Shift+S",
        }
    )

    with pytest.raises(ValidationError):
        KeyboardShortcutProfile.model_validate(payload)

import pytest

from pydantic import ValidationError

from backend.app.models.system_settings import SettingType
from backend.app.services import keyboard_shortcut_catalog
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


def test_keyboard_shortcut_catalog_filters_uninstalled_pack_manifests(
    monkeypatch,
):
    monkeypatch.setattr(
        keyboard_shortcut_catalog,
        "_get_installed_pack_ids",
        lambda: {"installed_demo"},
    )
    monkeypatch.setattr(
        keyboard_shortcut_catalog,
        "_scan_pack_yaml_files",
        lambda: [
            {
                "id": "installed_demo",
                "code": "installed_demo",
                "display_name": "Installed Demo",
                "workspace_tools": [
                    {
                        "id": "open_panel",
                        "label": "Open Panel",
                        "shortcut": "F8",
                        "slot": "workbench.left_tool_rail",
                    }
                ],
            },
            {
                "id": "not_installed_demo",
                "code": "not_installed_demo",
                "display_name": "Not Installed Demo",
                "workspace_tools": [
                    {
                        "id": "hidden_panel",
                        "label": "Hidden Panel",
                        "shortcut": "F7",
                    }
                ],
            },
        ],
    )

    catalog = keyboard_shortcut_catalog.build_keyboard_shortcut_catalog()

    assert len(catalog) == 1
    assert catalog[0]["owner_id"] == "installed_demo"
    assert catalog[0]["owner_label"] == "Installed Demo"
    assert catalog[0]["binding_id"] == (
        "workspace_tool:installed_demo:open_panel:open"
    )

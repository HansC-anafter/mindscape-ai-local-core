from datetime import datetime, timezone

from backend.app.models.system_settings import SettingType
from backend.app.services.system_settings_crud import SystemSettingsCRUDMixin
from backend.app.services.system_settings_defaults import SystemSettingsDefaultsMixin
from backend.app.services.system_settings_profile_bindings import (
    SystemSettingsProfileBindingsMixin,
)
from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.services.system_settings_utils import _utc_now


def test_system_settings_store_facade_keeps_domain_mixins():
    assert SystemSettingsStore.__mro__[1:4] == (
        SystemSettingsDefaultsMixin,
        SystemSettingsCRUDMixin,
        SystemSettingsProfileBindingsMixin,
    )


def test_system_settings_store_facade_exports_legacy_methods():
    expected = {
        "_init_default_settings": (
            "SystemSettingsDefaultsMixin._init_default_settings"
        ),
        "_serialize_value": "SystemSettingsCRUDMixin._serialize_value",
        "get_setting": "SystemSettingsCRUDMixin.get_setting",
        "save_setting": "SystemSettingsCRUDMixin.save_setting",
        "set_setting": "SystemSettingsCRUDMixin.set_setting",
        "set_capability_profile_mapping": (
            "SystemSettingsProfileBindingsMixin.set_capability_profile_mapping"
        ),
        "get_profile_model_bindings": (
            "SystemSettingsProfileBindingsMixin.get_profile_model_bindings"
        ),
    }

    for method_name, qualname in expected.items():
        assert getattr(SystemSettingsStore, method_name).__qualname__ == qualname


def test_system_settings_store_serialization_helpers_keep_existing_behavior():
    store = object.__new__(SystemSettingsStore)

    serialized = store._serialize_value({"label": "traditional"}, SettingType.JSON)
    assert serialized == '{"label": "traditional"}'
    assert store._deserialize_value(serialized, SettingType.JSON) == {
        "label": "traditional"
    }
    assert store._deserialize_value("[1, 2]", SettingType.ARRAY) == [1, 2]
    assert store._deserialize_value("bad-int", SettingType.INTEGER) == 0
    assert store._deserialize_value("bad-float", SettingType.FLOAT) == 0.0
    assert store._deserialize_value("yes", SettingType.BOOLEAN) is True
    assert store._deserialize_value("0", SettingType.BOOLEAN) is False
    assert store._coerce_datetime("not-a-date").tzinfo is timezone.utc
    assert store._coerce_datetime(datetime(2026, 1, 1)) == datetime(2026, 1, 1)


def test_system_settings_profile_binding_helpers_keep_existing_normalization():
    assert SystemSettingsStore._normalize_profile_bindings_entry(
        {
            " local-chat ": " gpt-5.4 ",
            "": "ignored",
            "vision": "",
            123: "ignored",
        }
    ) == {"local-chat": "gpt-5.4"}

    assert SystemSettingsStore._normalize_profile_model_bindings(
        {
            " local ": {"chat": " model-a "},
            "cloud": "not-a-dict",
            "": {"ignored": "value"},
        }
    ) == {"local": {"chat": "model-a"}, "cloud": {}}


def test_system_settings_profile_binding_setter_preserves_local_cloud_defaults():
    class FakeStore(SystemSettingsStore):
        def __init__(self):
            self.saved = []

        def set_setting(self, **kwargs):
            self.saved.append(kwargs)

    store = FakeStore()
    store.set_profile_model_bindings({"local": {"chat": "model-a"}})

    assert store.saved == [
        {
            "key": "profile_model_bindings",
            "value": {"local": {"chat": "model-a"}, "cloud": {}},
            "value_type": SettingType.JSON,
            "category": "llm",
            "description": "Deployment-scoped capability profile to model bindings",
        }
    ]


def test_system_settings_utc_now_helper_is_timezone_aware():
    assert _utc_now().tzinfo is timezone.utc

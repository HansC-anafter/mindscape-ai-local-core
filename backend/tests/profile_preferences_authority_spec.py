import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.dependencies import auth
from backend.app.services.profile_preferences import (
    ProfilePreferencesConflictError,
    ProfilePreferencesMutationService,
    ProfilePreferencesPatchRequest,
)
from backend.app.services.profile_preferences_core.projection import (
    resolve_ui_language_projection,
)
from backend.app.services.stores.postgres.profile_preferences_store import (
    ProfilePreferencesPatchAttempt,
    ProfilePreferencesRecord,
)
from backend.app.services.workspace_locale_seed import (
    resolve_workspace_default_locale,
)


def test_ui_locale_projection_has_one_deterministic_fallback_chain():
    assert resolve_ui_language_projection(
        preferences={"preferred_ui_language": "ja"},
        version=7,
        system_default_language="en",
    ).model_dump() == {"locale": "ja", "version": 7, "source": "profile"}
    assert resolve_ui_language_projection(
        preferences={"preferred_ui_language": "fr"},
        version=8,
        system_default_language="en",
    ).model_dump() == {
        "locale": "en",
        "version": 8,
        "source": "system_seed",
    }
    assert resolve_ui_language_projection(
        preferences={},
        version=9,
        system_default_language="fr",
    ).model_dump() == {
        "locale": "zh-TW",
        "version": 9,
        "source": "hard_default",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_version": 1},
        {"expected_version": 1, "preferred_ui_language": None},
        {"expected_version": 1, "preferred_ui_language": "fr"},
        {"expected_version": 1, "unknown_preference": True},
    ],
)
def test_preferences_patch_rejects_empty_null_unsupported_and_unknown_fields(
    payload,
):
    with pytest.raises(ValidationError):
        ProfilePreferencesPatchRequest(**payload)


def test_preferences_service_performs_one_store_patch_without_event_side_effect():
    calls = []

    class _Store:
        def patch_preferences(self, **kwargs):
            calls.append(kwargs)
            return ProfilePreferencesPatchAttempt(
                record=ProfilePreferencesRecord(
                    preferences={
                        "preferred_ui_language": "en",
                        "unrelated_preference": "preserved",
                    },
                    version=4,
                    system_default_language="zh-TW",
                ),
                current_version=None,
            )

    service = ProfilePreferencesMutationService(store=_Store())
    request = ProfilePreferencesPatchRequest(
        expected_version=3,
        preferred_ui_language="en",
    )

    assert service.patch_preferences("user-1", request).model_dump() == {
        "locale": "en",
        "version": 4,
        "source": "profile",
    }
    assert calls == [
        {
            "profile_id": "user-1",
            "expected_version": 3,
            "patch": {"preferred_ui_language": "en"},
        }
    ]


def test_preferences_service_returns_the_current_version_on_cas_conflict():
    class _Store:
        def patch_preferences(self, **_kwargs):
            return ProfilePreferencesPatchAttempt(
                record=None,
                current_version=12,
            )

    service = ProfilePreferencesMutationService(store=_Store())
    request = ProfilePreferencesPatchRequest(
        expected_version=3,
        enable_habit_suggestions=True,
    )

    with pytest.raises(ProfilePreferencesConflictError) as exc_info:
        service.patch_preferences("user-1", request)
    assert exc_info.value.current_version == 12


def test_current_identity_does_not_load_the_workspace_projection(monkeypatch):
    workspace_reads = []
    monkeypatch.setattr(auth, "is_cloud_mode", lambda: False)
    monkeypatch.setattr(auth, "get_default_user_id", lambda: "local-user")
    monkeypatch.setattr(
        auth,
        "_get_local_workspace_ids",
        lambda _user_id: workspace_reads.append(True) or ["workspace-1"],
    )
    request = SimpleNamespace(headers={}, state=SimpleNamespace())

    context = asyncio.run(auth.get_current_identity(request))

    assert context.user_id == "local-user"
    assert context.workspace_ids == []
    assert workspace_reads == []


def test_workspace_locale_seed_is_content_policy_not_ui_policy():
    class _Store:
        def get_profile(self, user_id, apply_habits):
            assert user_id == "owner-1"
            assert apply_habits is False
            return SimpleNamespace(
                preferences=SimpleNamespace(
                    preferred_ui_language="ja",
                    preferred_content_language="en",
                )
            )

    assert resolve_workspace_default_locale(
        explicit_locale=None,
        owner_user_id="owner-1",
        profile_store=_Store(),
    ) == "en"
    assert resolve_workspace_default_locale(
        explicit_locale="ja",
        owner_user_id="owner-1",
        profile_store=_Store(),
    ) == "ja"

"""Pure locale projection rules shared by reads and successful mutations."""

from typing import Any

from .schemas import ProfileUiLanguageProjection, UiLocale

HARD_DEFAULT_UI_LOCALE: UiLocale = "zh-TW"
SUPPORTED_UI_LOCALES = frozenset({"zh-TW", "en", "ja"})


def _supported_locale(value: Any) -> UiLocale | None:
    if isinstance(value, str) and value in SUPPORTED_UI_LOCALES:
        return value  # type: ignore[return-value]
    return None


def resolve_ui_language_projection(
    *,
    preferences: dict,
    version: int,
    system_default_language: Any,
) -> ProfileUiLanguageProjection:
    """Resolve profile preference, then system seed, then the hard default."""
    profile_locale = _supported_locale(preferences.get("preferred_ui_language"))
    if profile_locale is not None:
        return ProfileUiLanguageProjection(
            locale=profile_locale,
            version=version,
            source="profile",
        )

    system_locale = _supported_locale(system_default_language)
    if system_locale is not None:
        return ProfileUiLanguageProjection(
            locale=system_locale,
            version=version,
            source="system_seed",
        )

    return ProfileUiLanguageProjection(
        locale=HARD_DEFAULT_UI_LOCALE,
        version=version,
        source="hard_default",
    )

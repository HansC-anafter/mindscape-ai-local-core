"""Workspace content-locale seed policy."""

from typing import Any

HARD_DEFAULT_WORKSPACE_LOCALE = "zh-TW"


def resolve_workspace_default_locale(
    *,
    explicit_locale: str | None,
    owner_user_id: str,
    profile_store: Any,
) -> str:
    """Resolve explicit locale, owner content preference, then hard default."""
    if isinstance(explicit_locale, str) and explicit_locale.strip():
        return explicit_locale.strip()

    profile = profile_store.get_profile(owner_user_id, apply_habits=False)
    if profile is not None:
        owner_locale = getattr(
            getattr(profile, "preferences", None),
            "preferred_content_language",
            None,
        )
        if isinstance(owner_locale, str) and owner_locale.strip():
            return owner_locale.strip()

    return HARD_DEFAULT_WORKSPACE_LOCALE

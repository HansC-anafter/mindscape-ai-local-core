"""Strict API schemas for current-profile preference reads and writes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models.mindscape_profile import ReviewPreferences

UiLocale = Literal["zh-TW", "en", "ja"]
UiLocaleSource = Literal["profile", "system_seed", "hard_default"]


class ProfileUiLanguageProjection(BaseModel):
    """Resolved UI locale plus the profile version used for CAS writes."""

    locale: UiLocale
    version: int = Field(ge=1)
    source: UiLocaleSource


class ProfilePreferencesPatchRequest(BaseModel):
    """Allowlisted, partial current-profile preference mutation."""

    expected_version: int = Field(ge=1)
    preferred_ui_language: UiLocale | None = None
    enable_habit_suggestions: bool | None = None
    review_preferences: ReviewPreferences | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_preference_update(self):
        if not any(
            field_name in self.model_fields_set
            for field_name in (
                "preferred_ui_language",
                "enable_habit_suggestions",
                "review_preferences",
            )
        ):
            raise ValueError("At least one preference field is required")
        if any(
            getattr(self, field_name) is None
            for field_name in self.model_fields_set
            if field_name != "expected_version"
        ):
            raise ValueError("Preference fields cannot be null")
        return self

    def preference_patch(self) -> dict:
        """Return only allowlisted fields explicitly supplied by the caller."""
        return self.model_dump(
            exclude={"expected_version"},
            exclude_unset=True,
            exclude_none=True,
            mode="json",
        )

"""Internal seams for the current-profile preferences authority."""

from .mutation import (
    ProfilePreferencesConflictError,
    ProfilePreferencesMutationService,
    ProfilePreferencesNotFoundError,
    ProfileUiLanguageProjectionService,
)
from .schemas import (
    ProfilePreferencesPatchRequest,
    ProfileUiLanguageProjection,
    UiLocale,
)

__all__ = [
    "ProfilePreferencesConflictError",
    "ProfilePreferencesMutationService",
    "ProfilePreferencesNotFoundError",
    "ProfilePreferencesPatchRequest",
    "ProfileUiLanguageProjectionService",
    "ProfileUiLanguageProjection",
    "UiLocale",
]

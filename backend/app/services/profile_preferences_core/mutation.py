"""Application service for current-profile preference projection and CAS writes."""

from backend.app.services.stores.postgres.profile_preferences_store import (
    PostgresProfilePreferencesStore,
)

from .projection import resolve_ui_language_projection
from .schemas import (
    ProfilePreferencesPatchRequest,
    ProfileUiLanguageProjection,
)


class ProfilePreferencesNotFoundError(LookupError):
    """The authenticated identity has no profile row."""


class ProfilePreferencesConflictError(RuntimeError):
    """The supplied profile version is stale."""

    def __init__(self, current_version: int):
        super().__init__("Profile preferences version conflict")
        self.current_version = current_version


class ProfileUiLanguageProjectionService:
    """Read-only application seam for the authenticated locale projection."""

    def __init__(self, store: PostgresProfilePreferencesStore | None = None):
        self._store = store or PostgresProfilePreferencesStore()

    def get_ui_language(self, profile_id: str) -> ProfileUiLanguageProjection:
        record = self._store.get_projection_record(profile_id)
        if record is None:
            raise ProfilePreferencesNotFoundError(profile_id)
        return resolve_ui_language_projection(
            preferences=record.preferences,
            version=record.version,
            system_default_language=record.system_default_language,
        )


class ProfilePreferencesMutationService:
    """Single application seam for allowlisted preference CAS writes."""

    def __init__(self, store: PostgresProfilePreferencesStore | None = None):
        self._store = store or PostgresProfilePreferencesStore()

    def patch_preferences(
        self,
        profile_id: str,
        request: ProfilePreferencesPatchRequest,
    ) -> ProfileUiLanguageProjection:
        attempt = self._store.patch_preferences(
            profile_id=profile_id,
            expected_version=request.expected_version,
            patch=request.preference_patch(),
        )
        if attempt.record is not None:
            return resolve_ui_language_projection(
                preferences=attempt.record.preferences,
                version=attempt.record.version,
                system_default_language=attempt.record.system_default_language,
            )
        if attempt.current_version is None:
            raise ProfilePreferencesNotFoundError(profile_id)
        raise ProfilePreferencesConflictError(attempt.current_version)

"""Postgres adaptation of ProfilesStore."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.mindscape import MindscapeProfile, UserPreferences

logger = logging.getLogger(__name__)


class PostgresProfilesStore(PostgresStoreBase):
    """Postgres implementation of ProfilesStore."""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__()
        self.db_path = db_path

    def create_profile(self, profile: MindscapeProfile) -> MindscapeProfile:
        """Create a new profile."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO profiles (
                    id, name, email, roles, domains, preferences,
                    onboarding_state, self_description, created_at, updated_at, version
                ) VALUES (
                    :id, :name, :email, :roles, :domains, :preferences,
                    :onboarding_state, :self_description, :created_at, :updated_at, :version
                )
            """
            )
            params = {
                "id": profile.id,
                "name": profile.name,
                "email": profile.email,
                "roles": self.serialize_json(profile.roles),
                "domains": self.serialize_json(profile.domains),
                "preferences": self.serialize_json(
                    profile.preferences.dict() if profile.preferences else {}
                ),
                "onboarding_state": (
                    self.serialize_json(profile.onboarding_state)
                    if profile.onboarding_state
                    else None
                ),
                "self_description": (
                    self.serialize_json(profile.self_description)
                    if profile.self_description
                    else None
                ),
                "created_at": profile.created_at,
                "updated_at": profile.updated_at,
                "version": profile.version,
            }
            conn.execute(query, params)
            logger.info(f"Created profile: {profile.id}")
            return profile

    def get_profile(
        self, profile_id: str, apply_habits: bool = True
    ) -> Optional[MindscapeProfile]:
        """
        Get profile by ID.

        Args:
            profile_id: Profile ID
            apply_habits: If True, apply confirmed habits to preferences (default: True)
        """
        with self.get_connection() as conn:
            query = text("SELECT * FROM profiles WHERE id = :id")
            result = conn.execute(query, {"id": profile_id})
            row = result.fetchone()
            if not row:
                return None

            profile = self._row_to_profile(row)

            if apply_habits:
                try:
                    from backend.app.services.habit_store import HabitStore

                    habit_store = HabitStore()
                    profile = habit_store.apply_confirmed_habits(profile)
                except Exception as e:
                    logger.warning(
                        f"Failed to apply confirmed habits to profile {profile_id}: {e}"
                    )

            return profile

    def update_profile(
        self, profile_id: str, updates: Dict[str, Any]
    ) -> Optional[MindscapeProfile]:
        """Update profile."""
        # Fetch existing to merge updates and check existence
        # Note: We need to do this carefully within transaction ideally,
        # or implement optimistic locking properly using version.

        # Here we follow the pattern: fetch, update object in memory, optimistic check in SQL.
        # But for valid 'updates' dict applying, we largely trust the caller or fetch first.

        # Let's fetch first to get current state (without habits applied, raw state)
        current = self.get_profile(profile_id, apply_habits=False)
        if not current:
            return None

        # Apply updates to current object in memory
        for key, value in updates.items():
            if hasattr(current, key):
                setattr(current, key, value)

        current.updated_at = datetime.utcnow()
        current.version += 1

        with self.transaction() as conn:
            query = text(
                """
                UPDATE profiles
                SET name = :name,
                    email = :email,
                    roles = :roles,
                    domains = :domains,
                    preferences = :preferences,
                    onboarding_state = :onboarding_state,
                    self_description = :self_description,
                    updated_at = :updated_at,
                    version = :version
                WHERE id = :id
            """
            )
            params = {
                "name": current.name,
                "email": current.email,
                "roles": self.serialize_json(current.roles),
                "domains": self.serialize_json(current.domains),
                "preferences": self.serialize_json(
                    current.preferences.dict() if current.preferences else {}
                ),
                "onboarding_state": (
                    self.serialize_json(current.onboarding_state)
                    if current.onboarding_state
                    else None
                ),
                "self_description": (
                    self.serialize_json(current.self_description)
                    if current.self_description
                    else None
                ),
                "updated_at": current.updated_at,
                "version": current.version,
                "id": profile_id,
            }
            conn.execute(query, params)
            return current

    def _row_to_profile(self, row) -> MindscapeProfile:
        """Convert database row to MindscapeProfile."""
        return MindscapeProfile(
            id=row.id,
            name=row.name,
            email=row.email,
            roles=self.deserialize_json(row.roles, []),
            domains=self.deserialize_json(row.domains, []),
            preferences=UserPreferences(**self.deserialize_json(row.preferences, {})),
            onboarding_state=(
                self.deserialize_json(row.onboarding_state)
                if row.onboarding_state
                else None
            ),
            self_description=(
                self.deserialize_json(row.self_description)
                if row.self_description
                else None
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=row.version or 1,
        )

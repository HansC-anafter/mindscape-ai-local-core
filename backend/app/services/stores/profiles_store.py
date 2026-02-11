"""
Profiles store for Mindscape data persistence
Handles profile CRUD operations
"""

from typing import Optional, Dict, Any
from backend.app.services.stores.base import StoreBase
from ...models.mindscape import MindscapeProfile
import logging

logger = logging.getLogger(__name__)


class ProfilesStore(StoreBase):
    """Store for managing profiles"""

    def create_profile(self, profile: MindscapeProfile) -> MindscapeProfile:
        """Create a new profile"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO profiles (id, name, email, roles, domains, preferences, onboarding_state, self_description, created_at, updated_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                profile.id,
                profile.name,
                profile.email,
                self.serialize_json(profile.roles),
                self.serialize_json(profile.domains),
                self.serialize_json(profile.preferences.dict() if profile.preferences else {}),
                self.serialize_json(profile.onboarding_state) if profile.onboarding_state else None,
                self.serialize_json(profile.self_description) if profile.self_description else None,
                self.to_isoformat(profile.created_at),
                self.to_isoformat(profile.updated_at),
                profile.version
            ))
            conn.commit()
            return profile

    def get_profile(self, profile_id: str, apply_habits: bool = True) -> Optional[MindscapeProfile]:
        """
        Get profile by ID

        Args:
            profile_id: Profile ID
            apply_habits: If True, apply confirmed habits to preferences (default: True)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM profiles WHERE id = ?', (profile_id,))
            row = cursor.fetchone()
            if not row:
                return None

            profile = self._row_to_profile(row)

            if apply_habits:
                try:
                    from backend.app.services.habit_store import HabitStore
                    habit_store = HabitStore(self.db_path)
                    profile = habit_store.apply_confirmed_habits(profile)
                except Exception as e:
                    logger.warning(f"Failed to apply confirmed habits to profile {profile_id}: {e}")

            return profile

    def update_profile(self, profile_id: str, updates: Dict[str, Any]) -> Optional[MindscapeProfile]:
        """Update profile"""
        profile = self.get_profile(profile_id)
        if not profile:
            return None

        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        from datetime import datetime, timezone
        profile.updated_at = _utc_now()
        profile.version += 1

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE profiles
                SET name = ?, email = ?, roles = ?, domains = ?, preferences = ?,
                    onboarding_state = ?, self_description = ?, updated_at = ?, version = ?
                WHERE id = ?
            ''', (
                profile.name,
                profile.email,
                self.serialize_json(profile.roles),
                self.serialize_json(profile.domains),
                self.serialize_json(profile.preferences.dict() if profile.preferences else {}),
                self.serialize_json(profile.onboarding_state) if profile.onboarding_state else None,
                self.serialize_json(profile.self_description) if profile.self_description else None,
                self.to_isoformat(profile.updated_at),
                profile.version,
                profile.id
            ))
            conn.commit()
            return profile

    def _row_to_profile(self, row) -> MindscapeProfile:
        """Convert database row to MindscapeProfile"""
        from ...models.mindscape import UserPreferences
        return MindscapeProfile(
            id=row['id'],
            name=row['name'],
            email=row['email'],
            roles=self.deserialize_json(row['roles'], []),
            domains=self.deserialize_json(row['domains'], []),
            preferences=UserPreferences(**self.deserialize_json(row['preferences'], {})),
            onboarding_state=self.deserialize_json(row['onboarding_state']) if row['onboarding_state'] else None,
            self_description=self.deserialize_json(row['self_description']) if row['self_description'] else None,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at']),
            version=row['version']
        )

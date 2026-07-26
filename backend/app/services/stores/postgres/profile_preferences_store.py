"""Bounded PostgreSQL projection and CAS mutation for profile preferences."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase


@dataclass(frozen=True)
class ProfilePreferencesRecord:
    preferences: dict
    version: int
    system_default_language: Any


@dataclass(frozen=True)
class ProfilePreferencesPatchAttempt:
    record: ProfilePreferencesRecord | None
    current_version: int | None


class PostgresProfilePreferencesStore(PostgresStoreBase):
    """One-statement read and one-statement successful preference update."""

    _PROJECTION_SQL = text(
        """
        SELECT
            p.preferences,
            p.version,
            (
                SELECT value
                FROM system_settings
                WHERE key = 'default_language'
            ) AS system_default_language
        FROM profiles AS p
        WHERE p.id = :profile_id
        """
    )

    _PATCH_SQL = text(
        """
        UPDATE profiles
        SET
            preferences = (
                COALESCE(NULLIF(preferences, ''), '{}')::jsonb
                || CAST(:patch AS jsonb)
            )::text,
            updated_at = NOW(),
            version = version + 1
        WHERE id = :profile_id
          AND version = :expected_version
        RETURNING
            preferences,
            version,
            (
                SELECT value
                FROM system_settings
                WHERE key = 'default_language'
            ) AS system_default_language
        """
    )

    _VERSION_SQL = text(
        "SELECT version FROM profiles WHERE id = :profile_id"
    )

    @staticmethod
    def _preferences_dict(raw_preferences: Any) -> dict:
        if isinstance(raw_preferences, dict):
            return raw_preferences
        if not isinstance(raw_preferences, str):
            raise ValueError("Profile preferences must be a JSON object")
        parsed = json.loads(raw_preferences or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("Profile preferences must be a JSON object")
        return parsed

    @classmethod
    def _record_from_row(cls, row) -> ProfilePreferencesRecord:
        return ProfilePreferencesRecord(
            preferences=cls._preferences_dict(row["preferences"]),
            version=int(row["version"]),
            system_default_language=row["system_default_language"],
        )

    def get_projection_record(
        self, profile_id: str
    ) -> ProfilePreferencesRecord | None:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    self._PROJECTION_SQL,
                    {"profile_id": profile_id},
                )
                .mappings()
                .fetchone()
            )
        return self._record_from_row(row) if row is not None else None

    def patch_preferences(
        self,
        *,
        profile_id: str,
        expected_version: int,
        patch: dict,
    ) -> ProfilePreferencesPatchAttempt:
        with self.transaction() as conn:
            row = (
                conn.execute(
                    self._PATCH_SQL,
                    {
                        "profile_id": profile_id,
                        "expected_version": expected_version,
                        "patch": json.dumps(patch, ensure_ascii=False),
                    },
                )
                .mappings()
                .fetchone()
            )
            if row is not None:
                return ProfilePreferencesPatchAttempt(
                    record=self._record_from_row(row),
                    current_version=None,
                )

            current_row = (
                conn.execute(
                    self._VERSION_SQL,
                    {"profile_id": profile_id},
                )
                .mappings()
                .fetchone()
            )
            current_version = (
                int(current_row["version"]) if current_row is not None else None
            )
            return ProfilePreferencesPatchAttempt(
                record=None,
                current_version=current_version,
            )

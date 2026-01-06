"""
Control Profile Store

Manages persistence of Control Profile configurations for workspaces.
"""

import json
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from ...models.control_knob import ControlProfile
from ...services.knob_presets import PRESETS

logger = logging.getLogger(__name__)


class ControlProfileStore:
    """Store for Control Profile configurations"""

    def __init__(self, db_path: str):
        """
        Initialize Control Profile Store

        Args:
            db_path: Path to database directory
        """
        self.db_path = Path(db_path)
        self.profiles_dir = self.db_path / "control_profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def _get_profile_path(self, workspace_id: str) -> Path:
        """Get file path for workspace control profile"""
        return self.profiles_dir / f"{workspace_id}.json"

    def get_control_profile(self, workspace_id: str) -> Optional[ControlProfile]:
        """
        Get control profile for workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            ControlProfile if exists, None otherwise
        """
        profile_path = self._get_profile_path(workspace_id)
        if not profile_path.exists():
            return None

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return ControlProfile(**data)
        except Exception as e:
            logger.error(f"Failed to load control profile for {workspace_id}: {e}", exc_info=True)
            return None

    def save_control_profile(
        self,
        workspace_id: str,
        profile: ControlProfile,
        updated_by: Optional[str] = None
    ) -> ControlProfile:
        """
        Save control profile for workspace

        Args:
            workspace_id: Workspace ID
            profile: ControlProfile to save
            updated_by: User ID who updated this profile

        Returns:
            Saved ControlProfile
        """
        try:
            # Ensure workspace_id matches
            profile.workspace_id = workspace_id
            profile.updated_at = datetime.now().isoformat()

            profile_path = self._get_profile_path(workspace_id)
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile.model_dump(exclude_none=True), f, indent=2, ensure_ascii=False)

            logger.info(f"Saved control profile for workspace {workspace_id}")
            return profile
        except Exception as e:
            logger.error(f"Failed to save control profile for {workspace_id}: {e}", exc_info=True)
            raise

    def delete_control_profile(self, workspace_id: str) -> bool:
        """
        Delete control profile for workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            True if deleted, False if not found
        """
        profile_path = self._get_profile_path(workspace_id)
        if not profile_path.exists():
            return False

        try:
            profile_path.unlink()
            logger.info(f"Deleted control profile for workspace {workspace_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete control profile for {workspace_id}: {e}", exc_info=True)
            raise

    def get_or_create_default_profile(self, workspace_id: str, preset_id: str = "advisor") -> ControlProfile:
        """
        Get existing profile or create default from preset

        Args:
            workspace_id: Workspace ID
            preset_id: Preset ID to use for default (default: "advisor")

        Returns:
            ControlProfile
        """
        existing = self.get_control_profile(workspace_id)
        if existing:
            return existing

        # Create from preset
        preset = PRESETS.get(preset_id, PRESETS["advisor"])
        preset.workspace_id = workspace_id
        preset.created_at = datetime.now().isoformat()
        preset.updated_at = datetime.now().isoformat()

        return self.save_control_profile(workspace_id, preset)


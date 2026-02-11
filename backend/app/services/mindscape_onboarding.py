"""
Mindscape Onboarding Service
Handles the cold-start onboarding flow for new users
"""

from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, Optional
from backend.app.models.mindscape import MindscapeProfile
from backend.app.services.mindscape_store import MindscapeStore


class MindscapeOnboardingService:
    """Service for managing mindscape onboarding flow"""

    def __init__(self, store: MindscapeStore):
        self.store = store

    def get_onboarding_status(self, profile_id: str) -> Dict[str, Any]:
        """
        Get onboarding status for a profile

        Onboarding is only when NO state exists. Once user has workspace, intent, or profile data,
        they are no longer in onboarding mode but in continuous state update mode.
        """
        profile = self.store.get_profile(profile_id)

        # Check if user has any state (workspace, intent, or self_description)
        import logging
        logger = logging.getLogger(__name__)

        workspaces = []
        intents = []

        try:
            workspaces = self.store.list_workspaces(owner_user_id=profile_id, limit=1)
        except Exception as e:
            logger.warning(f"Failed to check workspaces for {profile_id}: {e}", exc_info=True)
            workspaces = []

        try:
            from backend.app.models.mindscape import IntentStatus
            all_intents = self.store.list_intents(profile_id=profile_id, status=IntentStatus.ACTIVE)
            intents = all_intents[:1] if all_intents else []
        except Exception as e:
            logger.warning(f"Failed to check intents for {profile_id}: {e}", exc_info=True)
            intents = []

        logger.info(f"State check for {profile_id}: {len(workspaces)} workspaces, {len(intents)} active intents")

        has_state = (
            len(workspaces) > 0 or
            len(intents) > 0 or
            (profile and profile.self_description)
        )

        logger.info(f"Profile {profile_id} has_state: {has_state} (workspaces: {len(workspaces)}, intents: {len(intents)}, self_description: {bool(profile and profile.self_description)})")

        if has_state:
            # User has state, not onboarding - return current state with auto-completion
            if profile and profile.onboarding_state:
                # Create new dict to ensure is_onboarding and has_state are set correctly
                result = dict(profile.onboarding_state)
                result["is_onboarding"] = False
                result["has_state"] = True
                return result
            else:
                # Has state but no onboarding_state record - auto-complete task1
                return {
                    "is_onboarding": False,
                    "has_state": True,
                    "task1_completed": True,  # Auto-complete if has workspace
                    "task2_completed": False,
                    "task3_completed": False,
                    "task1_completed_at": None,
                    "task2_completed_at": None,
                    "task3_completed_at": None
                }

        # True onboarding: no state at all
        if not profile or not profile.onboarding_state:
            return {
                "task1_completed": False,
                "task2_completed": False,
                "task3_completed": False,
                "task1_completed_at": None,
                "task2_completed_at": None,
                "task3_completed_at": None,
                "is_onboarding": True,
                "has_state": False
            }

        # Profile exists with onboarding_state but no actual state (workspace/intent)
        # Create new dict to ensure is_onboarding and has_state are set correctly
        result = dict(profile.onboarding_state)
        result["is_onboarding"] = True
        result["has_state"] = False
        return result

    def complete_task1_self_intro(
        self,
        profile_id: str,
        identity: str,
        solving: str,
        thinking: str
    ) -> Dict[str, Any]:
        """
        Complete task 1: Self introduction / Starter role card

        Args:
            profile_id: User profile ID
            identity: What the user is currently doing (現在主要在做什麼)
            solving: What they want to accomplish (最近想搞定什麼事)
            thinking: What's on their mind (遇到什麼卡點或在想什麼)

        Returns:
            Updated profile dict with onboarding_state
        """
        # Get or create profile
        profile = self.store.get_profile(profile_id)

        if not profile:
            # Create new profile if doesn't exist
            profile = MindscapeProfile(
                id=profile_id,
                name="Default User",
                email=None,
                roles=[],
                domains=[],
                created_at=_utc_now(),
                updated_at=_utc_now()
            )
            profile = self.store.create_profile(profile)

        # Update self description
        profile.self_description = {
            "identity": identity,
            "solving": solving,
            "thinking": thinking,
            "created_at": _utc_now().isoformat()
        }

        # Initialize or update onboarding state
        if not profile.onboarding_state:
            profile.onboarding_state = {
                "task1_completed": False,
                "task2_completed": False,
                "task3_completed": False,
                "task1_completed_at": None,
                "task2_completed_at": None,
                "task3_completed_at": None,
            }

        profile.onboarding_state["task1_completed"] = True
        profile.onboarding_state["task1_completed_at"] = _utc_now().isoformat()

        # Save to database
        updated_profile = self.store.update_profile(
            profile_id,
            {
                "self_description": profile.self_description,
                "onboarding_state": profile.onboarding_state
            }
        )

        return {
            "success": True,
            "task": "task1",
            "profile": {
                "id": updated_profile.id,
                "name": updated_profile.name,
                "self_description": updated_profile.self_description,
                "onboarding_state": updated_profile.onboarding_state
            }
        }

    def complete_task2_project_breakdown(
        self,
        profile_id: str,
        execution_id: Optional[str] = None,
        intent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete task 2: First long-term project breakdown

        Args:
            profile_id: User profile ID
            execution_id: Playbook execution ID (optional)
            intent_id: Created intent card ID (optional)

        Returns:
            Updated profile dict with onboarding_state
        """
        profile = self.store.get_profile(profile_id)

        if not profile:
            raise ValueError(f"Profile {profile_id} not found")

        # Initialize or update onboarding state
        if not profile.onboarding_state:
            profile.onboarding_state = {
                "task1_completed": False,
                "task2_completed": False,
                "task3_completed": False,
                "task1_completed_at": None,
                "task2_completed_at": None,
                "task3_completed_at": None,
            }

        profile.onboarding_state["task2_completed"] = True
        profile.onboarding_state["task2_completed_at"] = _utc_now().isoformat()

        if execution_id:
            profile.onboarding_state["task2_execution_id"] = execution_id
        if intent_id:
            profile.onboarding_state["task2_intent_id"] = intent_id

        # Save to database
        updated_profile = self.store.update_profile(
            profile_id,
            {"onboarding_state": profile.onboarding_state}
        )

        return {
            "success": True,
            "task": "task2",
            "onboarding_state": updated_profile.onboarding_state
        }

    def complete_task3_weekly_review(
        self,
        profile_id: str,
        execution_id: Optional[str] = None,
        created_seeds_count: int = 0
    ) -> Dict[str, Any]:
        """
        Complete task: Weekly work rhythm review

        Args:
            profile_id: User profile ID
            execution_id: Playbook execution ID (optional)
            created_seeds_count: Number of seeds created (optional)

        Returns:
            Updated profile dict with onboarding_state
        """
        profile = self.store.get_profile(profile_id)

        if not profile:
            raise ValueError(f"Profile {profile_id} not found")

        # Initialize or update onboarding state
        if not profile.onboarding_state:
            profile.onboarding_state = {
                "task1_completed": False,
                "task2_completed": False,
                "task3_completed": False,
                "task1_completed_at": None,
                "task2_completed_at": None,
                "task3_completed_at": None,
            }

        profile.onboarding_state["task3_completed"] = True
        profile.onboarding_state["task3_completed_at"] = _utc_now().isoformat()

        if execution_id:
            profile.onboarding_state["task3_execution_id"] = execution_id
        if created_seeds_count > 0:
            profile.onboarding_state["task3_seeds_count"] = created_seeds_count

        # Save to database
        updated_profile = self.store.update_profile(
            profile_id,
            {"onboarding_state": profile.onboarding_state}
        )

        return {
            "success": True,
            "task": "task3",
            "onboarding_state": updated_profile.onboarding_state
        }

    def is_onboarding_complete(self, profile_id: str) -> bool:
        """Check if all onboarding tasks are completed"""
        status = self.get_onboarding_status(profile_id)
        return (
            status.get("task1_completed", False) and
            status.get("task2_completed", False) and
            status.get("task3_completed", False)
        )

    def get_completion_count(self, profile_id: str) -> int:
        """Get number of completed onboarding tasks"""
        status = self.get_onboarding_status(profile_id)
        count = 0
        if status.get("task1_completed", False):
            count += 1
        if status.get("task2_completed", False):
            count += 1
        if status.get("task3_completed", False):
            count += 1
        return count

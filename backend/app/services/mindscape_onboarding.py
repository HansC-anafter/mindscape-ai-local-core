"""
Mindscape Onboarding Service
Handles the cold-start onboarding flow for new users
"""

from datetime import datetime
from typing import Dict, Any, Optional
from backend.app.models.mindscape import MindscapeProfile
from backend.app.services.mindscape_store import MindscapeStore


class MindscapeOnboardingService:
    """Service for managing mindscape onboarding flow"""

    def __init__(self, store: MindscapeStore):
        self.store = store

    def get_onboarding_status(self, profile_id: str) -> Dict[str, Any]:
        """Get onboarding status for a profile"""
        profile = self.store.get_profile(profile_id)

        if not profile or not profile.onboarding_state:
            # Return default state for new users
            return {
                "task1_completed": False,
                "task2_completed": False,
                "task3_completed": False,
                "task1_completed_at": None,
                "task2_completed_at": None,
                "task3_completed_at": None,
            }

        return profile.onboarding_state

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
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            profile = self.store.create_profile(profile)

        # Update self description
        profile.self_description = {
            "identity": identity,
            "solving": solving,
            "thinking": thinking,
            "created_at": datetime.utcnow().isoformat()
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
        profile.onboarding_state["task1_completed_at"] = datetime.utcnow().isoformat()

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
        profile.onboarding_state["task2_completed_at"] = datetime.utcnow().isoformat()

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
        profile.onboarding_state["task3_completed_at"] = datetime.utcnow().isoformat()

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

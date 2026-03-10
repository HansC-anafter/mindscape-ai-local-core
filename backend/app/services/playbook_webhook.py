"""
Playbook Webhook Handler
Handles post-execution webhooks for playbooks
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import uuid

from app.database.config import get_vector_postgres_config
from backend.app.models.mindscape import IntentCard, IntentStatus, PriorityLevel
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.mindscape_onboarding import MindscapeOnboardingService

logger = logging.getLogger(__name__)


class PlaybookWebhookHandler:
    """Handle playbook completion webhooks"""

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.onboarding_service = MindscapeOnboardingService(store)

    async def handle_playbook_completion(
        self,
        execution_id: str,
        playbook_code: str,
        user_id: str,
        output_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle playbook completion and trigger appropriate actions

        Args:
            execution_id: Execution ID
            playbook_code: Playbook code (e.g., 'project_breakdown_onboarding')
            user_id: User profile ID
            output_data: Structured output from playbook execution

        Returns:
            Dictionary with created resources and updated state
        """
        logger.info(f"Handling playbook completion: {playbook_code} for profile {user_id}")

        result = {
            "success": True,
            "playbook_code": playbook_code,
            "execution_id": execution_id,
            "created_resources": {}
        }

        try:
            # Check if this is an onboarding playbook
            if playbook_code == "project_breakdown_onboarding":
                result.update(await self._handle_task2_completion(
                    execution_id, user_id, output_data
                ))
            elif playbook_code == "weekly_review_onboarding":
                result.update(await self._handle_task3_completion(
                    execution_id, user_id, output_data
                ))
            else:
                # Regular playbook completion
                result.update(await self._handle_regular_playbook(
                    execution_id, playbook_code, user_id, output_data
                ))

            # Observe habits from webhook completion (background, don't block response)
            try:
                await self._observe_habits_from_webhook(
                    profile_id=user_id,
                    playbook_code=playbook_code,
                    execution_id=execution_id,
                    output_data=output_data
                )
            except Exception as e:
                logger.warning(f"Failed to observe habits from webhook: {e}")

            return result

        except Exception as e:
            logger.error(f"Failed to handle playbook completion: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _handle_task2_completion(
        self,
        execution_id: str,
        user_id: str,
        output_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Task 2 (project breakdown) completion"""
        logger.info(f"Handling Task 2 completion for profile {user_id}")

        # Extract project data from output
        project_data = output_data.get("project_data", {})

        if not project_data:
            raise ValueError("No project_data found in output")

        # Create intent card
        intent = IntentCard(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=project_data.get("title", "未命名專案"),
            description=project_data.get("description", ""),
            status=IntentStatus.ACTIVE,
            priority=PriorityLevel.HIGH,
            tags=["onboarding", "project"],
            metadata={
                "source": "onboarding_task2",
                "execution_id": execution_id,
                "goal": project_data.get("goal"),
                "steps": project_data.get("steps", []),
                "next_action": project_data.get("next_action"),
                "estimated_duration": project_data.get("estimated_duration")
            },
            created_at=_utc_now(),
            updated_at=_utc_now()
        )

        created_intent = self.store.create_intent(intent)
        logger.info(f"Created intent card: {created_intent.id}")

        # Update onboarding state
        onboarding_result = self.onboarding_service.complete_task2_project_breakdown(
            user_id=user_id,
            execution_id=execution_id,
            intent_id=created_intent.id
        )

        # Extract and store seeds (if any)
        extracted_insights = output_data.get("extracted_insights", {})
        seeds_created = 0

        if extracted_insights:
            seeds_created = await self._create_seeds_from_insights(
                user_id=user_id,
                insights=extracted_insights,
                source_id=execution_id,
                source_type="onboarding_task2"
            )

        return {
            "created_resources": {
                "intent_id": created_intent.id,
                "intent_title": created_intent.title,
                "seeds_created": seeds_created
            },
            "onboarding_state": onboarding_result.get("onboarding_state")
        }

    async def _handle_task3_completion(
        self,
        execution_id: str,
        user_id: str,
        output_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Task 3 (weekly review) completion"""
        logger.info(f"Handling Task 3 completion for profile {user_id}")

        # Extract seeds from output
        extracted_seeds = output_data.get("extracted_seeds", [])

        if not extracted_seeds:
            logger.warning("No extracted_seeds found in output")

        # Create seeds
        seeds_created = 0
        for seed_data in extracted_seeds:
            try:
                await self._create_seed(
                    user_id=user_id,
                    source_type="onboarding_task3",
                    content=seed_data.get("content", ""),
                    metadata=seed_data.get("metadata", {}),
                    confidence=seed_data.get("confidence", 0.7),
                    source_id=execution_id
                )
                seeds_created += 1
            except Exception as e:
                logger.error(f"Failed to create seed: {e}")

        logger.info(f"Created {seeds_created} seeds")

        # Update onboarding state
        onboarding_result = self.onboarding_service.complete_task3_weekly_review(
            user_id=user_id,
            execution_id=execution_id,
            created_seeds_count=seeds_created
        )

        return {
            "created_resources": {
                "seeds_created": seeds_created
            },
            "onboarding_state": onboarding_result.get("onboarding_state"),
            "is_onboarding_complete": onboarding_result.get("onboarding_state", {}).get("task3_completed", False)
        }

    async def _handle_regular_playbook(
        self,
        execution_id: str,
        playbook_code: str,
        user_id: str,
        output_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle regular (non-onboarding) playbook completion"""
        logger.info(f"Handling regular playbook: {playbook_code}")

        # TODO: Implement regular playbook handling
        # - Extract seeds from output
        # - Create/update intent cards if needed
        # - Generate suggestions

        return {
            "created_resources": {},
            "message": "Regular playbook handling not yet implemented"
        }

    async def _create_seeds_from_insights(
        self,
        user_id: str,
        insights: Dict[str, Any],
        source_id: str,
        source_type: str
    ) -> int:
        """Create seeds from extracted insights"""
        seeds_created = 0

        # Extract working style seeds
        working_style = insights.get("user_working_style")
        if working_style:
            await self._create_seed(
                user_id=user_id,
                source_type=source_type,
                content=f"工作風格：{working_style}",
                confidence=0.7,
                source_id=source_id
            )
            seeds_created += 1

        # Extract potential blockers as seeds
        blockers = insights.get("potential_blockers", [])
        for blocker in blockers:
            await self._create_seed(
                user_id=user_id,
                source_type=source_type,
                content=f"潛在障礙：{blocker}",
                confidence=0.6,
                source_id=source_id
            )
            seeds_created += 1

        return seeds_created

    async def _create_seed(
        self,
        user_id: str,
        source_type: str,
        content: str,
        confidence: float,
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a single seed in the database"""
        try:
            import psycopg2

            postgres_config = {
                **get_vector_postgres_config(),
            }

            with psycopg2.connect(**postgres_config) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO mindscape_personal (
                        id, user_id, source_type, content, metadata,
                        source_type, source_id, confidence, weight, updated_at, created_at
                    ) VALUES (
                        gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                ''', (
                    user_id,
                    source_type,
                    content,
                    json.dumps(metadata or {}),
                    source_type,
                    source_id,
                    confidence,
                    1.0  # default weight
                ))
                conn.commit()
                logger.info(f"Created seed: {source_type} - {content}")

        except Exception as e:
            logger.error(f"Failed to create seed: {e}")
            raise

    async def _observe_habits_from_webhook(
        self,
        profile_id: str,
        playbook_code: str,
        execution_id: str,
        output_data: Dict[str, Any]
    ):
        """
        從 Webhook 完成事件中觀察習慣

        Args:
            profile_id: Profile ID
            playbook_code: Playbook 程式碼
            execution_id: 執行 ID
            output_data: 輸出資料
        """
        try:
            from backend.app.capabilities.habit_learning.services.habit_observer import HabitObserver
            from backend.app.capabilities.habit_learning.services.habit_candidate_generator import HabitCandidateGenerator
            from backend.app.services.mindscape_store import MindscapeStore

            # Check if habit learning is enabled
            store = MindscapeStore()
            profile = store.get_profile(profile_id, apply_habits=False)  # Don't apply habits for check
            if profile and profile.preferences:
                if not getattr(profile.preferences, 'enable_habit_suggestions', False):
                    logger.debug(f"Habit suggestions disabled for profile {profile_id}, skipping webhook observation")
                    return

            # Create observer and generator
            observer = HabitObserver()
            generator = HabitCandidateGenerator()

            # Get conversation length from output_data if available
            conversation_length = output_data.get("conversation_length", 0)

            # Observe habits from webhook completion
            observations = await observer.observe_playbook_execution(
                profile_id=profile_id,
                playbook_code=playbook_code,
                profile=profile,
                conversation_length=conversation_length,
                execution_id=execution_id
            )

            # For each observation, check if we should generate a candidate
            for obs in observations:
                try:
                    generator.process_observation(
                        observation_id=obs.id,
                        profile_id=obs.profile_id,
                        habit_key=obs.habit_key,
                        habit_value=obs.habit_value,
                        habit_category=obs.habit_category
                    )
                except Exception as e:
                    logger.warning(f"Failed to process observation {obs.id}: {e}")

        except ImportError:
            logger.debug("Habit learning modules not available, skipping webhook observation")
        except Exception as e:
            logger.warning(f"Failed to observe habits from webhook: {e}", exc_info=True)

"""Habit observation helpers for the agent runner facade."""

import logging
from typing import Optional

from backend.app.models.mindscape import AgentExecution, MindscapeProfile

logger = logging.getLogger(__name__)


async def extract_seeds_from_execution(
    profile_id: str,
    execution_id: str,
    task: str,
    output: Optional[str] = None,
) -> None:
    """Placeholder for execution seed extraction."""
    return None


async def observe_habits_from_execution(
    runner,
    profile_id: str,
    execution: AgentExecution,
    profile: Optional[MindscapeProfile] = None,
) -> None:
    """Observe habits from agent execution and generate candidates if needed."""
    try:
        from backend.app.capabilities.habit_learning.services.habit_candidate_generator import (
            HabitCandidateGenerator,
        )
        from backend.app.capabilities.habit_learning.services.habit_observer import (
            HabitObserver,
        )

        if profile and profile.preferences:
            if not getattr(profile.preferences, "enable_habit_suggestions", False):
                logger.debug("Habit suggestions disabled for profile %s", profile_id)
                return

        observer = HabitObserver(runner.store.db_path)
        generator = HabitCandidateGenerator(runner.store.db_path)

        observations = await observer.observe_agent_execution(
            profile_id=profile_id, execution=execution, profile=profile
        )

        for observation in observations:
            try:
                generator.process_observation(
                    observation_id=observation.id,
                    profile_id=observation.profile_id,
                    habit_key=observation.habit_key,
                    habit_value=observation.habit_value,
                    habit_category=observation.habit_category,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to process observation %s: %s", observation.id, exc
                )

    except ImportError:
        logger.debug("Habit learning modules not available, skipping habit observation")
    except Exception as exc:
        logger.warning(
            "Failed to observe habits from execution: %s", exc, exc_info=True
        )

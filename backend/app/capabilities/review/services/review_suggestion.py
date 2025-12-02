"""
Review Suggestion Service
Review reminder service: check if user should be reminded to review
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ....services.mindscape_store import MindscapeStore
from ....services.habit_store import HabitStore
from ....models.mindscape import ReviewPreferences

logger = logging.getLogger(__name__)


@dataclass
class ReviewSuggestion:
    """Review suggestion"""
    since: datetime
    until: datetime
    total_entries: int
    insight_events: int


@dataclass
class ObservationStats:
    """Observation statistics"""
    total_entries: int
    insight_events: int


class ReviewSuggestionService:
    """Review reminder service"""

    def __init__(self, db_path: str = None):
        self.mindscape_store = MindscapeStore(db_path)
        self.habit_store = HabitStore(db_path)

    def maybe_suggest_review(self, profile_id: str) -> Optional[ReviewSuggestion]:
        """
        Check if user should be reminded to review

        Logic:
        1. Read profile.review_preferences
        2. Check if time has come (based on cadence)
        3. Check if there are enough entries / insight_events
        4. If all conditions are met, return ReviewSuggestion

        Args:
            profile_id: Profile ID

        Returns:
            ReviewSuggestion or None
        """
        try:
            # Get profile
            profile = self.mindscape_store.get_profile(profile_id)
            if not profile or not profile.preferences:
                return None

            prefs = profile.preferences.review_preferences
            if not prefs:
                return None

            # If cadence is manual, don't auto-remind
            if prefs.cadence == "manual":
                return None

            # Get last review time
            last_review_at = self._get_last_review_time(profile_id)

            # Check if time has come
            now = datetime.utcnow()
            if not self._is_time_for_review(now, last_review_at, prefs):
                return None

            # Get statistics
            stats = self._get_observation_stats_since(profile_id, last_review_at or profile.created_at)

            # Check if there are enough entries / insight_events
            if stats.total_entries < prefs.min_entries:
                return None

            if stats.insight_events < prefs.min_insight_events:
                return None

            # If all conditions are met, return suggestion
            return ReviewSuggestion(
                since=last_review_at or profile.created_at,
                until=now,
                total_entries=stats.total_entries,
                insight_events=stats.insight_events,
            )

        except Exception as e:
            logger.error(f"Failed to check review suggestion: {e}", exc_info=True)
            return None

    def _get_observation_stats_since(
        self,
        profile_id: str,
        since: datetime
    ) -> ObservationStats:
        """
        Get observation statistics since a certain time point

        Args:
            profile_id: Profile ID
            since: Start time

        Returns:
            ObservationStats
        """
        try:
            # Query all observations
            observations = self.habit_store.get_observations(profile_id, limit=1000)

            # Filter by time range
            filtered = [
                obs for obs in observations
                if obs.observed_at >= since
            ]

            # Statistics
            total_entries = len(filtered)
            insight_events = sum(1 for obs in filtered if obs.has_insight_signal)

            return ObservationStats(
                total_entries=total_entries,
                insight_events=insight_events,
            )

        except Exception as e:
            logger.error(f"Failed to get observation stats: {e}", exc_info=True)
            return ObservationStats(total_entries=0, insight_events=0)

    def _is_time_for_review(
        self,
        now: datetime,
        last_review_at: Optional[datetime],
        prefs: ReviewPreferences
    ) -> bool:
        """
        Check if it's time to remind

        Based on prefs.cadence:
        - "manual": always False
        - "weekly": check if more than a week has passed
        - "monthly": check if more than a month has passed

        Args:
            now: Current time
            last_review_at: Last review time (if not available, use profile.created_at)
            prefs: ReviewPreferences

        Returns:
            Whether it's time to remind
        """
        if prefs.cadence == "manual":
            return False

        # If no last review time, don't remind on first use (let user accumulate some data first)
        if not last_review_at:
            return False

        if prefs.cadence == "weekly":
            # Check if more than a week has passed
            days_since = (now - last_review_at).days
            if days_since >= 7:
                # Check if it's the specified day of week
                target_day = prefs.day_of_week
                current_day = now.weekday()  # 0=Monday, 6=Sunday
                return current_day == target_day
            return False

        elif prefs.cadence == "monthly":
            # Check if more than a month has passed
            days_since = (now - last_review_at).days
            if days_since >= 28:  # At least 28 days
                # Check if it's the specified day of month
                target_day = prefs.day_of_month
                current_day = now.day
                return current_day == target_day
            return False

        return False

    def _get_last_review_time(self, profile_id: str) -> Optional[datetime]:
        """
        Get last review time

        Currently read from profile's metadata or external storage
        Future: can create dedicated review_history table

        Args:
            profile_id: Profile ID

        Returns:
            Last review time, or None if not available
        """
        try:
            profile = self.mindscape_store.get_profile(profile_id)
            if not profile:
                return None

            # Read from profile's metadata or external storage
            # Currently return None (indicating first time)
            # Future can:
            # 1. Store in profile.metadata
            # 2. Create review_history table
            # 3. Infer from yearly_book execution records

            return None

        except Exception as e:
            logger.error(f"Failed to get last review time: {e}", exc_info=True)
            return None

    def record_review_completed(self, profile_id: str, review_time: Optional[datetime] = None):
        """
        Record that review has been completed

        Args:
            profile_id: Profile ID
            review_time: Review time (default: current time)
        """
        if review_time is None:
            review_time = datetime.utcnow()

        # Currently just log
        # Future: can store in profile.metadata or review_history table
        logger.info(f"Review completed for profile {profile_id} at {review_time.isoformat()}")

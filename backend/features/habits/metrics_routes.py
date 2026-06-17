"""Habit metrics route handlers."""

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.habit import HabitCandidateStatus, HabitMetricsResponse
from backend.features.habits.dependencies import habit_store, mindscape_store

router = APIRouter()


@router.get("/metrics", response_model=HabitMetricsResponse)
async def get_metrics(
    profile_id: str = Query(..., description="Profile ID")
) -> HabitMetricsResponse:
    """
    Get habit learning statistics

    Includes:
    - Total observation count
    - Candidate statistics (total, pending, confirmed, rejected)
    - Acceptance rate (confirmed / (confirmed + rejected))
    """
    try:
        all_candidates = habit_store.get_candidates(profile_id=profile_id, limit=10000)

        total_candidates = len(all_candidates)
        pending_candidates = sum(
            1 for c in all_candidates if c.status == HabitCandidateStatus.PENDING
        )
        confirmed_candidates = sum(
            1 for c in all_candidates if c.status == HabitCandidateStatus.CONFIRMED
        )
        rejected_candidates = sum(
            1 for c in all_candidates if c.status == HabitCandidateStatus.REJECTED
        )
        superseded_candidates = sum(
            1 for c in all_candidates if c.status == HabitCandidateStatus.SUPERSEDED
        )

        total_decisions = confirmed_candidates + rejected_candidates
        acceptance_rate = (
            (confirmed_candidates / total_decisions) if total_decisions > 0 else 0.0
        )

        observations = habit_store.get_observations(profile_id=profile_id, limit=10000)
        total_observations = len(observations)

        observations_with_candidates = set()
        for candidate in all_candidates:
            observations_with_candidates.update(candidate.evidence_refs[:10])

        candidate_hit_rate = (
            (len(observations_with_candidates) / total_observations)
            if total_observations > 0
            else 0.0
        )

        is_enabled = None
        try:
            profile = mindscape_store.get_profile(profile_id, apply_habits=False)
            if profile and profile.preferences:
                is_enabled = getattr(
                    profile.preferences, "enable_habit_suggestions", False
                )
        except Exception:
            pass

        return HabitMetricsResponse(
            total_observations=total_observations,
            total_candidates=total_candidates,
            pending_candidates=pending_candidates,
            confirmed_candidates=confirmed_candidates,
            rejected_candidates=rejected_candidates,
            acceptance_rate=acceptance_rate,
            candidate_hit_rate=candidate_hit_rate,
            is_habit_suggestions_enabled=is_enabled,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

"""
Review API routes
回顧提醒相關的 API 路由
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime

from backend.app.capabilities.review.services.review_suggestion import ReviewSuggestionService

router = APIRouter(tags=["review"])

# Initialize review suggestion service
review_service = ReviewSuggestionService()


@router.get("/suggestion")
async def get_review_suggestion(
    profile_id: str = Query(..., description="Profile ID")
):
    """
    取得回顧建議

    檢查是否應該提醒使用者進行回顧
    """
    try:
        suggestion = review_service.maybe_suggest_review(profile_id)
        if suggestion:
            return {
                "suggestion": {
                    "since": suggestion.since.isoformat(),
                    "until": suggestion.until.isoformat(),
                    "total_entries": suggestion.total_entries,
                    "insight_events": suggestion.insight_events,
                }
            }
        return {"suggestion": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get review suggestion: {str(e)}")


@router.post("/completed")
async def record_review_completed(
    profile_id: str = Query(..., description="Profile ID"),
    review_time: Optional[str] = Query(None, description="Review time (ISO format)")
):
    """
    記錄回顧已完成

    當使用者完成回顧後調用此 API
    """
    try:
        review_dt = None
        if review_time:
            review_dt = datetime.fromisoformat(review_time.replace('Z', '+00:00'))

        review_service.record_review_completed(profile_id, review_dt)
        return {"status": "recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record review completion: {str(e)}")

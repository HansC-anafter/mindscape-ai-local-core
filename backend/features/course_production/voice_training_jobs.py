"""
Voice Training Jobs API routes

Manages voice training job execution and status tracking
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, status, Depends
from fastapi.responses import StreamingResponse

from backend.app.models.course_production.voice_training_job import (
    VoiceTrainingJob,
    TrainingJobStatus
)
from backend.app.services.stores.course_production_store import CourseProductionStore
from backend.app.services.course_production.semantic_hub_integration import get_semantic_hub_client

router = APIRouter(
    tags=["course-production", "voice-training-jobs"]
)

logger = logging.getLogger(__name__)

# Store instance (singleton)
_store: Optional[CourseProductionStore] = None


def get_store() -> CourseProductionStore:
    """Get store instance"""
    global _store
    if _store is None:
        _store = CourseProductionStore()
    return _store


@router.get("", response_model=List[VoiceTrainingJob])
async def list_training_jobs(
    instructor_id: Optional[str] = Query(None, description="Filter by instructor"),
    voice_profile_id: Optional[str] = Query(None, description="Filter by voice profile"),
    status_filter: Optional[TrainingJobStatus] = Query(None, alias="status", description="Filter by status"),
    store: CourseProductionStore = Depends(get_store)
):
    """
    List training jobs with optional filters

    Args:
        instructor_id: Optional instructor filter
        voice_profile_id: Optional voice profile filter
        status_filter: Optional status filter
        store: Course production store

    Returns:
        List of training jobs
    """
    try:
        jobs = store.list_training_jobs(instructor_id, voice_profile_id, status_filter)
        return jobs
    except Exception as e:
        logger.error(f"Failed to list training jobs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list training jobs: {str(e)}"
        )


@router.get("/{job_id}", response_model=VoiceTrainingJob)
async def get_training_job(
    job_id: str = Path(..., description="Training job ID"),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Get training job details

    Args:
        job_id: Training job ID
        store: Course production store

    Returns:
        Training job details
    """
    try:
        job = store.get_training_job(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get training job: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get training job: {str(e)}"
        )


@router.get("/{job_id}/logs")
async def get_training_logs(
    job_id: str = Path(...),
    follow: bool = Query(False, description="Stream logs continuously")
):
    """
    Get training logs (streaming)

    Args:
        job_id: Training job ID
        follow: Whether to stream logs continuously

    Returns:
        Log content or stream
    """
    try:
        # TODO: Implement log retrieval from Semantic Hub
        # TODO: Support streaming if follow=True

        logs = f"Training logs for job {job_id}\n"

        if follow:
            # TODO: Implement Server-Sent Events (SSE) streaming
            def generate():
                yield logs
            return StreamingResponse(generate(), media_type="text/plain")
        else:
            return {"logs": logs}
    except Exception as e:
        logger.error(f"Failed to get training logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get training logs: {str(e)}"
        )


@router.post("/{job_id}/cancel", response_model=VoiceTrainingJob)
async def cancel_training_job(
    job_id: str = Path(...),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Cancel training job

    Args:
        job_id: Training job ID
        store: Course production store

    Returns:
        Updated training job with cancelled status
    """
    try:
        job = store.get_training_job(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )

        # Call Semantic Hub to cancel job
        semantic_client = get_semantic_hub_client()
        if semantic_client and semantic_client.is_configured():
            try:
                await semantic_client.cancel_training_job(job_id)
            except Exception as e:
                logger.warning(f"Failed to cancel job on Semantic Hub, updating local status: {e}")

        updated_job = store.update_training_job(job_id, {
            'status': TrainingJobStatus.CANCELLED.value
        })

        if not updated_job:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update job status"
            )

        return updated_job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel training job: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel training job: {str(e)}"
        )


@router.get("/{job_id}/status")
async def get_training_status(
    job_id: str = Path(...),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Get training job status (lightweight, for polling)

    Args:
        job_id: Training job ID
        store: Course production store

    Returns:
        Job status information
    """
    try:
        # Get local job record
        job = store.get_training_job(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )

        # Try to get latest status from Semantic Hub
        semantic_client = get_semantic_hub_client()
        if semantic_client and semantic_client.is_configured():
            try:
                semantic_status = await semantic_client.get_training_job_status(job_id)

                # Update local job status if changed
                semantic_status_value = semantic_status.get("status")
                if semantic_status_value and semantic_status_value != job.status.value:
                    store.update_training_job(job_id, {
                        'status': semantic_status_value
                    })
                    job.status = TrainingJobStatus(semantic_status_value)

                return {
                    "job_id": job_id,
                    "status": job.status.value,
                    "progress": semantic_status.get("progress", 0.0),
                    "estimated_completion": semantic_status.get("estimated_completion"),
                    "metrics": semantic_status.get("metrics")
                }
            except Exception as e:
                logger.warning(f"Failed to get status from Semantic Hub, using local status: {e}")

        # Fallback to local status
        return {
            "job_id": job_id,
            "status": job.status.value,
            "progress": 0.0
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get training status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get training status: {str(e)}"
        )

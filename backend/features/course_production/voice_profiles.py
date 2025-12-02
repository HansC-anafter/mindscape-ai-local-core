"""
Voice Profiles API routes

Manages voice profile metadata and training operations
"""

import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, Body, File, UploadFile, status, Depends
from fastapi.responses import JSONResponse

from backend.app.models.course_production.voice_profile import (
    VoiceProfile,
    VoiceProfileStatus,
    CreateVoiceProfileRequest,
    UpdateVoiceProfileRequest,
    StartTrainingRequest
)
from backend.app.models.course_production.voice_training_job import VoiceTrainingJob
from backend.app.services.stores.course_production_store import CourseProductionStore
from backend.app.services.course_production.file_storage import get_file_storage, CourseProductionFileStorage
from backend.app.services.course_production.semantic_hub_integration import get_semantic_hub_client

router = APIRouter(
    tags=["course-production", "voice-profiles"]
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


@router.get("", response_model=List[VoiceProfile])
async def list_voice_profiles(
    instructor_id: str = Query(..., description="Instructor ID"),
    status_filter: Optional[VoiceProfileStatus] = Query(None, alias="status", description="Filter by status"),
    store: CourseProductionStore = Depends(get_store)
):
    """
    List all voice profiles for an instructor

    Args:
        instructor_id: Instructor ID
        status_filter: Optional status filter
        store: Course production store

    Returns:
        List of voice profiles
    """
    try:
        profiles = store.list_voice_profiles(instructor_id, status_filter)
        return profiles
    except Exception as e:
        logger.error(f"Failed to list voice profiles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list voice profiles: {str(e)}"
        )


@router.post("", response_model=VoiceProfile, status_code=status.HTTP_201_CREATED)
async def create_voice_profile(
    request: CreateVoiceProfileRequest = Body(...),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Create a new voice profile (initialize)

    Args:
        request: Create voice profile request
        store: Course production store

    Returns:
        Created voice profile
    """
    try:
        profile = VoiceProfile(
            id=str(uuid.uuid4()),
            instructor_id=request.instructor_id,
            profile_name=request.profile_name,
            version=request.version or 1,
            status=VoiceProfileStatus.PENDING
        )

        created_profile = store.create_voice_profile(profile)
        return created_profile
    except Exception as e:
        logger.error(f"Failed to create voice profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create voice profile: {str(e)}"
        )


@router.get("/{profile_id}", response_model=VoiceProfile)
async def get_voice_profile(
    profile_id: str = Path(..., description="Voice profile ID"),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Get voice profile details

    Args:
        profile_id: Voice profile ID
        store: Course production store

    Returns:
        Voice profile details
    """
    try:
        profile = store.get_voice_profile(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voice profile {profile_id} not found"
            )
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get voice profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get voice profile: {str(e)}"
        )


@router.put("/{profile_id}", response_model=VoiceProfile)
async def update_voice_profile(
    profile_id: str = Path(...),
    request: UpdateVoiceProfileRequest = Body(...),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Update voice profile metadata

    Args:
        profile_id: Voice profile ID
        request: Update request
        store: Course production store

    Returns:
        Updated voice profile
    """
    try:
        updates = {}
        if request.profile_name is not None:
            updates['profile_name'] = request.profile_name
        if request.status is not None:
            updates['status'] = request.status.value
        if request.quality_score is not None:
            updates['quality_score'] = request.quality_score
        if request.similarity_score is not None:
            updates['similarity_score'] = request.similarity_score

        updated_profile = store.update_voice_profile(profile_id, updates)
        if not updated_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voice profile {profile_id} not found"
            )
        return updated_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update voice profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update voice profile: {str(e)}"
        )


@router.post("/{profile_id}/samples", status_code=status.HTTP_201_CREATED)
async def upload_sample(
    profile_id: str = Path(...),
    file: UploadFile = File(...),
    store: CourseProductionStore = Depends(get_store),
    file_storage: CourseProductionFileStorage = Depends(get_file_storage)
):
    """
    Upload sample file for voice profile training

    Args:
        profile_id: Voice profile ID
        file: Audio sample file
        store: Course production store
        file_storage: File storage service

    Returns:
        Upload result with file path
    """
    try:
        # Validate profile exists
        profile = store.get_voice_profile(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voice profile {profile_id} not found"
            )

        # Validate file type (audio files)
        allowed_types = ["audio/", "video/"]
        content_type = file.content_type or ""
        if not any(content_type.startswith(t) for t in allowed_types):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only audio/video files are allowed"
            )

        # Validate file size (max 50MB for samples)
        content = await file.read()
        file_size = len(content)
        max_size = 50 * 1024 * 1024  # 50MB
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {max_size / 1024 / 1024}MB"
            )

        # Reset file pointer for storage
        await file.seek(0)

        # Save file
        file_id, file_path = await file_storage.save_voice_sample(file, profile_id)

        # Update voice profile with sample path
        current_paths = profile.sample_paths or []
        current_paths.append(file_path)

        store.update_voice_profile(profile_id, {
            'sample_paths': current_paths,
            'sample_count': len(current_paths)
        })

        return {
            "success": True,
            "profile_id": profile_id,
            "file_id": file_id,
            "file_path": file_path,
            "file_size": file_size,
            "message": "Sample uploaded successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload sample: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload sample: {str(e)}"
        )


@router.post("/{profile_id}/train", response_model=VoiceTrainingJob, status_code=status.HTTP_202_ACCEPTED)
async def start_training(
    profile_id: str = Path(...),
    request: StartTrainingRequest = Body(...),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Start training task (calls Semantic Hub)

    Args:
        profile_id: Voice profile ID
        request: Training request with configuration
        store: Course production store

    Returns:
        Training job details
    """
    try:
        # Validate voice profile exists
        profile = store.get_voice_profile(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voice profile {profile_id} not found"
            )

        # Validate profile has samples
        if not profile.sample_paths or len(profile.sample_paths) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Voice profile has no samples. Please upload samples before training."
            )

        # Get Semantic Hub client
        semantic_client = get_semantic_hub_client()
        if not semantic_client or not semantic_client.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Semantic Hub is not configured or unavailable"
            )

        # Call Semantic Hub to start training
        try:
            training_result = await semantic_client.start_voice_training(
                profile_id=profile_id,
                sample_paths=profile.sample_paths,
                training_config=request.training_config,
                priority=request.priority or "normal"
            )

            # Extract job ID from Semantic Hub response
            semantic_job_id = training_result.get("job_id") or training_result.get("id")
            if not semantic_job_id:
                raise Exception("Semantic Hub did not return job_id")

        except Exception as e:
            logger.error(f"Semantic Hub training start failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to start training on Semantic Hub: {str(e)}"
            )

        # Create training job record in local database
        from backend.app.models.course_production.voice_training_job import (
            VoiceTrainingJob,
            TrainingJobStatus,
            TrainingJobPriority
        )

        job = VoiceTrainingJob(
            id=semantic_job_id,  # Use Semantic Hub job ID
            voice_profile_id=profile_id,
            instructor_id=profile.instructor_id,
            status=TrainingJobStatus.QUEUED,
            priority=TrainingJobPriority(request.priority or "normal"),
            training_config=request.training_config,
            sample_file_paths=profile.sample_paths,
            sample_metadata=[]  # TODO: Extract metadata from samples if needed
        )

        # Save job to database
        created_job = store.create_training_job(job)

        # Update voice profile with training job ID
        store.update_voice_profile(profile_id, {
            'training_job_id': semantic_job_id,
            'status': VoiceProfileStatus.TRAINING.value
        })

        logger.info(f"Training job started: {semantic_job_id} for profile {profile_id}")

        return created_job

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start training: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training: {str(e)}"
        )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_profile(
    profile_id: str = Path(...),
    store: CourseProductionStore = Depends(get_store)
):
    """
    Delete voice profile (mark as deprecated)

    Args:
        profile_id: Voice profile ID
        store: Course production store
    """
    try:
        success = store.delete_voice_profile(profile_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voice profile {profile_id} not found"
            )

        return JSONResponse(
            status_code=status.HTTP_204_NO_CONTENT,
            content=None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete voice profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete voice profile: {str(e)}"
        )

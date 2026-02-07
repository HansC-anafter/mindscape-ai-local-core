from fastapi import APIRouter, HTTPException, Depends
from backend.app.models.mindscape import MindscapeProfile
from backend.app.services.stores.profiles_store import ProfilesStore
from backend.app.services.mindscape_store import MindscapeStore
import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


def get_profiles_store():
    store = MindscapeStore()
    return ProfilesStore(store.db_path)


@router.get(
    "/{profile_id}",
    response_model=MindscapeProfile,
    summary="Get user profile",
    description="Get profile by ID",
)
async def get_profile(
    profile_id: str, store: ProfilesStore = Depends(get_profiles_store)
):
    profile = store.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put(
    "/{profile_id}",
    response_model=MindscapeProfile,
    summary="Update user profile",
    description="Update user profile data",
)
async def update_profile(
    profile_id: str,
    updates: Dict[str, Any],
    store: ProfilesStore = Depends(get_profiles_store),
):
    profile = store.update_profile(profile_id, updates)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

"""
Dependencies for FastAPI routes
Provides profile ID resolution for v0 MVP and future authentication
"""

from fastapi import Depends, Query, Header
from typing import Optional


async def get_current_profile_id(
    profile_id: Optional[str] = Query(None, description="Profile ID (v0 MVP optional)"),
    x_profile_id: Optional[str] = Header(None, alias="X-Profile-ID"),
) -> str:
    """
    Get current profile ID

    Priority:
    1. Query parameter: ?profile_id=xxx
    2. Header: X-Profile-ID
    3. Default: default-user (v0 MVP)

    v0 MVP: Returns default-user if not provided
    v1+: Must pass authentication
    """
    if profile_id:
        return profile_id
    if x_profile_id:
        return x_profile_id

    return "default-user"


async def get_optional_profile_id(
    profile_id: Optional[str] = Query(None),
    x_profile_id: Optional[str] = Header(None, alias="X-Profile-ID"),
) -> Optional[str]:
    """Optional profile ID (for some public APIs)"""
    return profile_id or x_profile_id



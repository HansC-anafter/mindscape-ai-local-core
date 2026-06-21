"""Profile and preference models for Mindscape."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CommunicationStyle(str, Enum):
    """User communication style preferences"""

    FORMAL = "formal"
    CASUAL = "casual"
    TECHNICAL = "technical"
    CONCISE = "concise"
    DETAILED = "detailed"


class ResponseLength(str, Enum):
    """Preferred response length"""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class ReviewPreferences(BaseModel):
    """Annual review preference settings"""

    cadence: str = Field(
        default="manual", description="Review cadence: 'manual' | 'weekly' | 'monthly'"
    )
    day_of_week: int = Field(
        default=6,
        ge=0,
        le=6,
        description="Day of week reminder (0=Mon ... 6=Sun, if weekly)",
    )
    day_of_month: int = Field(
        default=28, ge=1, le=31, description="Day of month reminder (if monthly)"
    )
    time_of_day: str = Field(
        default="21:00", description="Reminder time (e.g., '21:00' local time)"
    )
    min_entries: int = Field(
        default=10, ge=0, description="Minimum accumulated entries before reminder"
    )
    min_insight_events: int = Field(
        default=3,
        ge=0,
        description="Minimum 'has_insight_signal = True' events before reminder",
    )


class UserPreferences(BaseModel):
    """User preference settings"""

    communication_style: CommunicationStyle = CommunicationStyle.CASUAL
    response_length: ResponseLength = ResponseLength.MEDIUM
    language: str = "en"
    preferred_ui_language: str = Field(
        default="zh-TW", description="Preferred UI language (e.g., 'zh-TW', 'en')"
    )
    preferred_content_language: str = Field(
        default="zh-TW",
        description="Preferred content language for writing/working (e.g., 'zh-TW', 'en')",
    )
    secondary_languages: List[str] = Field(
        default_factory=list, description="Secondary languages the user can work with"
    )
    timezone: str = "UTC"
    enable_notifications: bool = True
    auto_save: bool = True
    theme: str = "light"
    enable_habit_suggestions: bool = Field(
        default=False,
        description="Enable habit learning and suggestions (default: False for privacy)",
    )
    review_preferences: ReviewPreferences = Field(
        default_factory=ReviewPreferences,
        description="Annual review preference settings",
    )


class MindscapeProfile(BaseModel):
    """User mindscape profile"""

    id: str = Field(..., description="Unique profile identifier")
    name: str = Field(..., description="Display name")
    email: Optional[str] = None
    roles: List[str] = Field(
        default_factory=list,
        description="User roles (e.g., developer, writer, entrepreneur)",
    )
    domains: List[str] = Field(
        default_factory=list,
        description="Expertise domains (e.g., tech, business, health)",
    )
    onboarding_state: Optional[Dict[str, Any]] = Field(
        default=None, description="Onboarding task completion state"
    )
    self_description: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User's self-description from onboarding (identity, solving, thinking)",
    )
    preferences: UserPreferences = Field(
        default_factory=UserPreferences, description="User preferences"
    )
    external_ref: Optional[Dict[str, Any]] = Field(
        default=None,
        description="External references (e.g., tenant_uuid, site_uuid) - optional, used by external extensions",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for profile categorization (e.g., 'wordpress-site-owner', 'agency')",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (e.g. memory services)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(
        default=1, description="Profile version for optimistic locking"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class CreateProfileRequest(BaseModel):
    """Request to create a new profile"""

    name: str
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    preferences: Optional[UserPreferences] = None


class UpdateProfileRequest(BaseModel):
    """Request to update an existing profile"""

    name: Optional[str] = None
    email: Optional[str] = None
    roles: Optional[List[str]] = None
    domains: Optional[List[str]] = None
    preferences: Optional[UserPreferences] = None

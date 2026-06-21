"""Entity and tag models for Mindscape."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    """Entity type enumeration"""

    PERSON = "person"
    PROJECT = "project"
    ARTIFACT = "artifact"
    THEME = "theme"


class TagCategory(str, Enum):
    """Tag category enumeration"""

    THEME = "theme"
    PHASE = "phase"
    MOOD = "mood"
    PRIORITY = "priority"
    RISK = "risk"


class Entity(BaseModel):
    """
    Core entity model for unified abstraction

    Entities represent the core "things" in the mindspace:
    - Person: People involved (users, contacts, collaborators)
    - Project: Work items, goals, initiatives
    - Artifact: Documents, files, outputs
    - Theme: Topics, categories, concepts
    """

    id: str = Field(..., description="Unique entity identifier")
    entity_type: EntityType = Field(..., description="Type of entity")
    name: str = Field(..., description="Entity name")
    profile_id: str = Field(..., description="Associated profile ID")
    description: Optional[str] = Field(None, description="Entity description")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (varies by entity_type)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class Tag(BaseModel):
    """
    Tag model for semantic labeling

    Tags are used to categorize and label entities with semantic meaning.
    Categories help organize tags by their purpose (theme, phase, mood, etc.)
    """

    id: str = Field(..., description="Unique tag identifier")
    name: str = Field(..., description="Tag name")
    category: TagCategory = Field(..., description="Tag category")
    profile_id: str = Field(..., description="Associated profile ID")
    description: Optional[str] = Field(None, description="Tag description")
    color: Optional[str] = Field(
        None, description="Optional color code for visualization"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class EntityTag(BaseModel):
    """
    Entity-Tag association model

    Links entities to tags with optional value.
    The value field allows tags to have associated data (e.g., priority level, phase status).
    """

    entity_id: str = Field(..., description="Entity ID")
    tag_id: str = Field(..., description="Tag ID")
    value: Optional[str] = Field(None, description="Optional tag value")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Association timestamp"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

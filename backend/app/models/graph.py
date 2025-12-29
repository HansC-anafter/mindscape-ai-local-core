"""
Graph models for Mind-Lens Graph feature

Design Principles:
- Independent graph nodes table (not extending Entity)
- Bridge tables for relationships (Entity, Playbook, Intent)
- Timezone-aware datetime (UTC)
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum


class GraphNodeCategory(str, Enum):
    """Graph node category"""
    DIRECTION = "direction"
    ACTION = "action"


class GraphNodeType(str, Enum):
    """Specific graph node types"""
    VALUE = "value"
    WORLDVIEW = "worldview"
    AESTHETIC = "aesthetic"
    KNOWLEDGE = "knowledge"
    STRATEGY = "strategy"
    ROLE = "role"
    RHYTHM = "rhythm"


class GraphRelationType(str, Enum):
    """Edge relation types"""
    SUPPORTS = "supports"
    CONFLICTS = "conflicts"
    DEPENDS_ON = "depends_on"
    RELATED_TO = "related_to"
    DERIVED_FROM = "derived_from"
    APPLIED_TO = "applied_to"


class LensNodeState(str, Enum):
    """Lens node execution state"""
    OFF = "off"
    KEEP = "keep"
    EMPHASIZE = "emphasize"


class GraphNode(BaseModel):
    """
    Mind-Lens Graph Node

    Represents a concept/value/preference in user's mindscape

    Note: Linked fields (linked_*) moved to bridge tables,
    these fields are read-only, populated dynamically from bridge tables in API responses

    Note: is_active represents node existence (soft delete flag), not execution state.
    Execution state (OFF/KEEP/EMPHASIZE) is stored in lens_profile_nodes.state.
    """
    id: str = Field(..., description="Unique node ID")
    profile_id: str = Field(..., description="Associated user ID")

    category: GraphNodeCategory = Field(..., description="Direction/Action")
    node_type: GraphNodeType = Field(..., description="Specific node type")

    label: str = Field(..., description="Node label (display name)")
    description: Optional[str] = Field(None, description="Detailed description")
    content: Optional[str] = Field(None, description="Long text content")

    icon: Optional[str] = Field(None, description="Emoji or icon")
    color: Optional[str] = Field(None, description="Node color")
    size: float = Field(default=1.0, description="Node size weight")

    is_active: bool = Field(default=True, description="Node existence flag (soft delete), not execution state")
    confidence: float = Field(default=1.0, ge=0, le=1, description="Confidence level")

    source_type: Optional[str] = Field(None, description="user_input/llm_extracted/imported")
    source_id: Optional[str] = Field(None, description="Source ID (e.g., workspace/conversation ID)")

    metadata: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class GraphNodeResponse(GraphNode):
    """
    GraphNode for API responses (includes relationships from bridge tables)

    These fields are read-only, populated by service layer from bridge tables
    """
    linked_entity_ids: List[str] = Field(default_factory=list, description="[Read-only] Linked Entity IDs")
    linked_playbook_codes: List[str] = Field(default_factory=list, description="[Read-only] Linked Playbook codes")
    linked_intent_ids: List[str] = Field(default_factory=list, description="[Read-only] Linked Intent IDs")


class GraphNodeCreate(BaseModel):
    """Request model for creating node (without id, timestamps, linked fields)"""
    category: GraphNodeCategory
    node_type: GraphNodeType
    label: str
    description: Optional[str] = None
    content: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    size: float = 1.0
    is_active: bool = True
    confidence: float = 1.0
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphNodeUpdate(BaseModel):
    """Request model for updating node (all fields optional)"""
    label: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    size: Optional[float] = None
    is_active: Optional[bool] = None
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class GraphEdge(BaseModel):
    """
    Mind-Lens Graph Edge

    Represents relationships between nodes
    """
    id: str = Field(..., description="Unique edge ID")
    profile_id: str = Field(..., description="Associated user ID")

    source_node_id: str = Field(..., description="Source node ID")
    target_node_id: str = Field(..., description="Target node ID")

    relation_type: GraphRelationType = Field(..., description="Edge relation type")

    weight: float = Field(default=1.0, ge=0, description="Edge weight")
    label: Optional[str] = Field(None, description="Edge label")

    is_active: bool = Field(default=True)

    metadata: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class GraphEdgeCreate(BaseModel):
    """Request model for creating edge"""
    source_node_id: str
    target_node_id: str
    relation_type: GraphRelationType
    weight: float = 1.0
    label: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdgeUpdate(BaseModel):
    """Request model for updating edge"""
    weight: Optional[float] = None
    label: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class LensProfileNode(BaseModel):
    """Preset node state configuration"""
    id: str
    preset_id: str
    node_id: str
    state: LensNodeState = Field(default=LensNodeState.KEEP)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class WorkspaceLensOverride(BaseModel):
    """Workspace-level lens override"""
    id: str
    workspace_id: str
    node_id: str
    state: LensNodeState
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class MindLensProfile(BaseModel):
    """
    Mind-Lens Profile Configuration

    Defines which graph nodes are active for a given workspace or scenario

    Note: active_node_ids is now a computed property derived from lens_profile_nodes.
    Legacy bridge table mind_lens_active_nodes is deprecated.
    """
    id: str
    profile_id: str
    name: str = Field(..., description="Lens name")
    description: Optional[str] = None

    is_default: bool = Field(default=False)

    active_node_ids: List[str] = Field(default_factory=list, description="[Read-only] Active node IDs (computed from lens_profile_nodes where state != 'off')")
    linked_workspace_ids: List[str] = Field(default_factory=list, description="[Read-only] Bound Workspace IDs (from bridge table)")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class MindLensProfileCreate(BaseModel):
    """Request model for creating lens profile"""
    name: str
    description: Optional[str] = None
    is_default: bool = False
    active_node_ids: List[str] = Field(default_factory=list)


class MindLensProfileUpdate(BaseModel):
    """Request model for updating lens profile"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    active_node_ids: Optional[List[str]] = None



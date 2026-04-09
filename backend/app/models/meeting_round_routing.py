"""
Round-level routing models for meeting deliberation trace.

These models intentionally stop at traceability. They do not alter the
current fixed facilitator -> planner -> critic execution order.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RoundGoal(BaseModel):
    """Facilitator-defined goal for the current deliberation round."""

    round_number: int
    owner_role_id: str = "facilitator"
    summary: str
    agenda_focus: List[str] = Field(default_factory=list)
    critical_constraints: List[str] = Field(default_factory=list)


class NeedDescriptor(BaseModel):
    """What a role needs before or during its turn."""

    id: str
    role_id: str
    need_type: str
    summary: str
    required: bool = True
    source_role_id: Optional[str] = None


class OfferDescriptor(BaseModel):
    """What a role can offer into the round routing graph."""

    id: str
    role_id: str
    offer_type: str
    summary: str
    packet_scope: Literal["global", "sparse"] = "sparse"
    content_preview: Optional[str] = None


class RoutedPacket(BaseModel):
    """Packet candidates that may be delivered to one or more roles."""

    id: str
    source_role_id: str
    packet_type: str
    summary: str
    packet_scope: Literal["global", "sparse"] = "sparse"
    consumer_role_ids: List[str] = Field(default_factory=list)
    content_preview: Optional[str] = None


class RoutingEdge(BaseModel):
    """Concrete routing edge selected for this round."""

    source_role_id: str
    target_role_id: str
    packet_ids: List[str] = Field(default_factory=list)
    matched_need_ids: List[str] = Field(default_factory=list)
    rationale: str


class RoundRoutingGraph(BaseModel):
    """Trace-only representation of the current round's routing graph."""

    session_id: str
    round_number: int
    goal: RoundGoal
    needs: List[NeedDescriptor] = Field(default_factory=list)
    offers: List[OfferDescriptor] = Field(default_factory=list)
    packets: List[RoutedPacket] = Field(default_factory=list)
    edges: List[RoutingEdge] = Field(default_factory=list)
    unmatched_need_ids: List[str] = Field(default_factory=list)
    unmatched_packet_ids: List[str] = Field(default_factory=list)
    fixed_speaker_order: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

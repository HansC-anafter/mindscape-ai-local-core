"""
Pydantic payload contracts for meeting-specific events.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AgentTurnPayload(BaseModel):
    meeting_session_id: str
    agent_id: str
    agent_role: str
    round_number: int
    content: str
    reasoning: Optional[str] = None
    cited_evidence: List[str] = Field(default_factory=list)


class DecisionProposalPayload(BaseModel):
    meeting_session_id: str
    proposed_by: str
    round_number: int
    proposal: str
    supporting_evidence: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)


class DecisionFinalPayload(BaseModel):
    meeting_session_id: str
    decided_by: str
    round_number: int
    decision: str
    rationale: str
    dissenting_views: List[str] = Field(default_factory=list)
    vote_result: Optional[Dict[str, str]] = None


class ActionItemPayload(BaseModel):
    meeting_session_id: str
    title: str
    description: str
    assigned_to: str
    priority: str = "medium"
    playbook_code: Optional[str] = None
    execution_id: Optional[str] = None


class MeetingRoundPayload(BaseModel):
    meeting_session_id: str
    round_number: int
    status: str
    speaker_order: List[str] = Field(default_factory=list)
    summary: str


class MemoryWritebackPayload(BaseModel):
    meeting_session_id: str
    memory_item_id: str
    digest_id: str
    writeback_run_id: str
    lifecycle_status: str
    verification_status: str
    project_id: Optional[str] = None

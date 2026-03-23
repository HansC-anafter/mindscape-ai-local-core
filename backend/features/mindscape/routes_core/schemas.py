"""Schemas for mindscape routes."""

from typing import Optional

from pydantic import BaseModel


class SelfIntroRequest(BaseModel):
    """Request body for onboarding self introduction."""

    identity: str
    solving: str
    thinking: str


class AnnotateIntentLogRequest(BaseModel):
    """Request body for annotating an intent log."""

    correct_interaction_type: Optional[str] = None
    correct_task_domain: Optional[str] = None
    correct_playbook_code: Optional[str] = None
    notes: Optional[str] = None


class ReplayIntentLogRequest(BaseModel):
    """Request body for replaying intent logs."""

    use_llm: Optional[bool] = None
    rule_priority: Optional[bool] = None
    model: Optional[str] = None

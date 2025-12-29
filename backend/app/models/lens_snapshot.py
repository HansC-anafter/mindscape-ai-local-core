"""
Lens Snapshot models for Mind-Lens observability.

Lens Snapshot captures the effective lens state at execution time for replay and analysis.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

from .lens_kernel import LensNode


class LensSnapshot(BaseModel):
    """Lens snapshot for replay"""
    id: str
    effective_lens_hash: str
    profile_id: str
    workspace_id: Optional[str]
    session_id: Optional[str]
    nodes: List[LensNode]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


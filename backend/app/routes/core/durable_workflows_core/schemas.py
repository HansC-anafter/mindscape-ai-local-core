"""Bounded request schemas for the durable review route seam."""

from pydantic import BaseModel, Field


class AsOfReference(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0, le=50)


class CompareRequest(BaseModel):
    left: AsOfReference
    right: AsOfReference

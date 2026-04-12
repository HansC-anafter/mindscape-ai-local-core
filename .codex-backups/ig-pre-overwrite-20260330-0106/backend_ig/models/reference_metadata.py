"""
Reference Metadata — Pydantic models for IG reference asset governance.

v1.2 schema: content_hash, aliases, analysis_provenance, analysis_job,
             usage_policy, soft-delete, controlled vocabulary auto_tags.

Aligned with:
  - FileChange.content_hash (SHA-256[:16])          → execution_trace.py
  - TaskStatus (PENDING/RUNNING/COMPLETED/FAILED)    → task_ir.py
  - ExternalJobNode (retry_count, output_fingerprint) → external_job_node.py
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_reference_id() -> str:
    return f"ref_{uuid4().hex[:8]}"


def _gen_job_id() -> str:
    return f"ref_job_{uuid4().hex[:8]}"


def content_hash_sha256(data: bytes) -> str:
    """SHA-256[:16] content hash — aligned with execution_trace._hash_file()."""
    return f"sha256:{hashlib.sha256(data).hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Alias(BaseModel):
    """Cross-account repost alias (same content_hash, different source)."""

    source_handle: str
    source_shortcode: str
    discovered_at: datetime = Field(default_factory=_utc_now)


class UsagePolicy(BaseModel):
    """Source attribution and usage constraints."""

    purpose: str = "internal_inspiration"
    exportable: bool = False
    attribution_required: bool = True


class AnalysisProvenance(BaseModel):
    """Full provenance for vision analysis results."""

    model_config = {"protected_namespaces": ()}

    schema_version: str = "1.0"
    model_id: str = ""
    tool_slot: str = "core_llm.multimodal_analyze"
    prompt_hash: str = ""
    validated_by: str = "VisionAnalysisSchema/pydantic"
    validated_at: Optional[datetime] = None
    normalizer_version: str = "tag_vocabulary@1.0"
    # v2.0 provenance fields
    analysis_profile: str = "aesthetic_core"  # aesthetic_core / portrait_deep / cinematic / product_material / visual_anatomy
    prompt_version: str = ""  # prompt template version identifier
    ocr_used: bool = False  # whether OCR was triggered during analysis
    evidence_enriched: bool = False
    evidence_enrichment_version: str = ""


class AnalysisJob(BaseModel):
    """Background analysis job — aligned with ExternalJobNode + TaskStatus."""

    job_id: str = Field(default_factory=_gen_job_id)
    status: str = "PENDING"  # PENDING / RUNNING / COMPLETED / FAILED
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status_updated_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    idempotency_key: str = ""

    def can_retry(self) -> bool:
        return self.status == "FAILED" and self.retry_count < self.max_retries

    @classmethod
    def create_pending(cls) -> "AnalysisJob":
        now = _utc_now()
        return cls(status="PENDING", queued_at=now, status_updated_at=now)

    def queue(self, *, reset_completed: bool = False) -> None:
        now = _utc_now()
        self.status = "PENDING"
        self.queued_at = now
        self.status_updated_at = now
        self.started_at = None
        if reset_completed:
            self.completed_at = None

    def start(self) -> None:
        now = _utc_now()
        self.status = "RUNNING"
        self.started_at = now
        self.status_updated_at = now

    def complete(self) -> None:
        now = _utc_now()
        self.status = "COMPLETED"
        self.completed_at = now
        self.status_updated_at = now

    def fail(self, error: str) -> None:
        now = _utc_now()
        self.status = "FAILED"
        self.last_error = error
        self.retry_count += 1
        self.status_updated_at = now

    def reset_for_retry(self) -> None:
        """FAILED → PENDING (auto-retry if retry_count < max_retries)."""
        if self.can_retry():
            self.queue()

    @staticmethod
    def make_idempotency_key(
        reference_id: str, content_hash: str, schema_version: str
    ) -> str:
        raw = f"{reference_id}:{content_hash}:{schema_version}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class AnalysisDebug(BaseModel):
    """Non-structured debug payload captured from the multimodal model."""

    raw_text: str = ""
    description_excerpt: str = ""
    thinking_text: str = ""
    failure_stage: str = ""
    failure_reason: str = ""
    captured_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Main metadata model
# ---------------------------------------------------------------------------


class ReferenceMetadata(BaseModel):
    """Complete reference metadata — v1.2 governance schema."""

    reference_id: str = Field(default_factory=_gen_reference_id)
    content_hash: str = ""
    source_fetch_etag: Optional[str] = None
    source_handle: str = ""
    source_shortcode: str = ""
    source_url: str = ""

    aliases: List[Alias] = Field(default_factory=list)

    pinned_at: datetime = Field(default_factory=_utc_now)
    pinned_by: str = ""

    # Soft-delete
    deleted: bool = False
    deleted_at: Optional[datetime] = None

    # Classification
    tags: List[str] = Field(default_factory=list)
    auto_tags: List[str] = Field(default_factory=list)
    collections: List[str] = Field(default_factory=list)

    # Project assignment
    project_id: Optional[str] = None

    # Carousel grouping
    carousel_index: Optional[int] = None        # 0-based index in carousel
    carousel_parent_id: Optional[str] = None    # reference_id of index-0 image
    carousel_total: Optional[int] = None         # total images in carousel

    # Post-level metadata (shared across carousel siblings)
    post_caption: Optional[str] = None
    post_like_count: Optional[int] = None
    post_comment_count: Optional[int] = None
    post_timestamp: Optional[str] = None

    # Attribution
    usage_policy: UsagePolicy = Field(default_factory=UsagePolicy)

    # Vision analysis results
    vision_description: Optional[Dict[str, Any]] = None
    training_annotations: Optional[Dict[str, Any]] = None
    analysis_provenance: Optional[AnalysisProvenance] = None
    analysis_job: Optional[AnalysisJob] = None
    analysis_debug: Optional[AnalysisDebug] = None

    def soft_delete(self) -> None:
        self.deleted = True
        self.deleted_at = _utc_now()

    def merge_tags(self, new_tags: List[str]) -> None:
        """Merge tags without duplicates."""
        existing = set(self.tags)
        for t in new_tags:
            if t not in existing:
                self.tags.append(t)
                existing.add(t)

    def add_alias(self, handle: str, shortcode: str) -> None:
        """Add cross-account repost alias."""
        for a in self.aliases:
            if a.source_handle == handle and a.source_shortcode == shortcode:
                return  # already exists
        self.aliases.append(Alias(source_handle=handle, source_shortcode=shortcode))

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, data: str) -> "ReferenceMetadata":
        return cls.model_validate_json(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReferenceMetadata":
        return cls.model_validate(data)

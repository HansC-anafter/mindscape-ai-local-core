"""
EGB Database Models

Persistent models: EGBRunIndex, EGBDriftReport, EGBIntentProfile

P0-B hard rule: egb_run_index must be able to reconstruct CorrelationIds
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, Index, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from typing import Optional, Dict, Any
import json

from backend.app.models import Base  # Use existing Base

logger = None  # Lazy import


class EGBRunIndex(Base):
    """
    EGB Run index table

    P0-B hard rule: Must be able to reconstruct CorrelationIds
    Design: Use correlation_ids_json to store complete CorrelationIds serialization

    P0-2 hard rule: success definition
    success = (trace.status == success) AND (strictness_level < 2 OR gate_L2_passed)
    """
    __tablename__ = "egb_run_index"

    # Primary key
    run_id = Column(String(255), primary_key=True, comment="Run ID (= trace_id, single source of truth)")

    # Basic associations
    workspace_id = Column(String(255), nullable=False, index=True, comment="Workspace ID")
    intent_id = Column(String(255), nullable=False, index=True, comment="Intent ID")
    decision_id = Column(String(255), nullable=True, index=True, comment="Decision ID")
    playbook_id = Column(String(255), nullable=True, index=True, comment="Playbook ID")

    # P0-B: Store complete CorrelationIds (JSON)
    correlation_ids_json = Column(JSON, nullable=False, comment="Complete CorrelationIds serialization (for reconstruction)")

    # Governance parameters (extracted from correlation_ids_json, for queries)
    strictness_level = Column(Integer, nullable=False, default=0, index=True, comment="Strictness level")
    mind_lens_level = Column(Integer, nullable=False, default=0, index=True, comment="Mind-Lens level")
    policy_version = Column(String(255), nullable=True, index=True, comment="Policy version")
    playbook_version = Column(String(255), nullable=True, comment="Playbook version")
    model_version = Column(String(255), nullable=True, comment="Model version")

    # Execution status
    status = Column(String(50), nullable=False, default="pending", index=True, comment="Execution status: pending/success/failed")
    gate_passed = Column(Boolean, nullable=False, default=False, comment="Whether StrictnessGate L2 passed")
    error_count = Column(Integer, nullable=False, default=0, comment="Error count")

    # P0-10 extension: RunOutcome (extends P0-2)
    outcome = Column(String(50), nullable=False, default="pending", index=True, comment="Execution outcome: success/failed/partial/pending_external/timeout")

    # P0-2/P0-10: success calculation field (for queries)
    is_success = Column(Boolean, nullable=False, default=False, index=True, comment="Whether successful (outcome==success)")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True, comment="Creation time")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="Update time")

    # Indexes
    __table_args__ = (
        Index("idx_intent_policy", "intent_id", "policy_version"),
        Index("idx_intent_strictness", "intent_id", "strictness_level"),
        Index("idx_workspace_intent", "workspace_id", "intent_id"),
        Index("idx_created_at", "created_at"),
    )

    def update_success(self) -> None:
        """
        Update is_success field (according to P0-2 and P0-10 rules)

        P0-10 extension: Consider RunOutcome
        - outcome == "success" → is_success = True
        - Others → is_success = False

        P0-2 backward compatibility: If outcome not set, use old rule
        - success = (status == "success") AND (strictness_level < 2 OR gate_passed)
        """
        # P0-10: Prefer outcome
        if self.outcome and self.outcome != "pending":
            self.is_success = (self.outcome == "success")
        else:
            # Fallback to P0-2 rule (backward compatibility)
            self.is_success = (
                self.status == "success" and
                (self.strictness_level < 2 or self.gate_passed)
            )


class ExternalJobMapping(Base):
    """
    External job to run mapping table

    P0-7 hard rule: Used to reattach external callbacks to the same run
    """
    __tablename__ = "egb_external_job_mapping"

    # Primary key
    mapping_id = Column(String(255), primary_key=True, comment="Mapping ID")

    # External system identification
    external_job_id = Column(String(255), nullable=False, index=True, comment="External system's job ID")
    external_run_id = Column(String(255), nullable=True, index=True, comment="External system's run ID (if available)")
    tool_name = Column(String(255), nullable=False, index=True, comment="Tool name (e.g., n8n, zapier, make)")

    # Association to your run
    run_id = Column(String(255), nullable=False, ForeignKey("egb_run_index.run_id"), index=True, comment="Your run_id")
    span_id = Column(String(255), nullable=True, index=True, comment="Optional: Which span to attach to")

    # Status tracking
    status = Column(String(50), nullable=False, default="pending", index=True, comment="Status: pending / running / success / failed / timeout")
    callback_received_at = Column(DateTime, nullable=True, comment="Callback received time")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True, comment="Creation time")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="Update time")

    # P0-10 extension: RunOutcome (extends P0-2)
    outcome = Column(String(50), nullable=True, index=True, comment="Execution outcome: success/failed/partial/pending_external/timeout (from EGBRunIndex association)")

    # Indexes
    __table_args__ = (
        Index("idx_external_job_id", "external_job_id"),
        Index("idx_run_id", "run_id"),
        Index("idx_tool_name", "tool_name"),
        Index("idx_status", "status"),
    )


class EGBDriftReport(Base):
    """
    EGB drift report table

    Stores calculated drift reports (optional, can also just cache)
    """
    __tablename__ = "egb_drift_report"

    # Primary key
    report_id = Column(String(255), primary_key=True, comment="Report ID")

    # Associations
    run_id = Column(String(255), nullable=False, index=True, comment="Current Run ID")
    baseline_run_id = Column(String(255), nullable=True, index=True, comment="Baseline Run ID")
    intent_id = Column(String(255), nullable=False, index=True, comment="Intent ID")
    workspace_id = Column(String(255), nullable=False, index=True, comment="Workspace ID")

    # Drift scores (JSON)
    drift_scores_json = Column(JSON, nullable=False, comment="DriftScores serialization")
    overall_drift_score = Column(Float, nullable=False, index=True, comment="Overall drift score")
    drift_level = Column(String(50), nullable=False, index=True, comment="Drift level: stable/low/moderate/high")

    # Semantic drift differences (JSON Pointer list)
    semantic_diff_pointers = Column(JSON, nullable=True, comment="Semantic drift diff pointers (JSON Pointer list)")

    # Drift explanations (JSON)
    drift_explanations_json = Column(JSON, nullable=True, comment="DriftExplanation list serialization")

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True, comment="Creation time")

    # Indexes
    __table_args__ = (
        Index("idx_intent_created", "intent_id", "created_at"),
        Index("idx_run_baseline", "run_id", "baseline_run_id"),
    )


class EGBIntentProfile(Base):
    """
    EGB intent evidence profile table

    Stores intent aggregated statistics (stability, cost, etc.)
    """
    __tablename__ = "egb_intent_profile"

    # Primary key
    profile_id = Column(String(255), primary_key=True, comment="Profile ID (usually intent_id:policy_version)")

    # Associations
    intent_id = Column(String(255), nullable=False, index=True, comment="Intent ID")
    workspace_id = Column(String(255), nullable=False, index=True, comment="Workspace ID")
    policy_version = Column(String(255), nullable=True, index=True, comment="Policy version")

    # Statistics
    total_runs = Column(Integer, nullable=False, default=0, comment="Total execution count")
    successful_runs = Column(Integer, nullable=False, default=0, comment="Successful count")
    failed_runs = Column(Integer, nullable=False, default=0, comment="Failed count")

    # Stability
    stability_score = Column(Float, nullable=False, default=1.0, index=True, comment="Stability score (0-1)")
    avg_drift_score = Column(Float, nullable=False, default=0.0, comment="Average drift score")

    # Cost statistics
    total_tokens = Column(Integer, nullable=False, default=0, comment="Total token count")
    total_cost_usd = Column(Float, nullable=False, default=0.0, comment="Total cost (USD)")
    avg_latency_ms = Column(Float, nullable=False, default=0.0, comment="Average latency (milliseconds)")

    # Time range
    first_run_at = Column(DateTime, nullable=True, comment="First execution time")
    last_run_at = Column(DateTime, nullable=True, index=True, comment="Last execution time")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="Creation time")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True, comment="Update time")

    # Indexes
    __table_args__ = (
        Index("idx_workspace_intent_policy", "workspace_id", "intent_id", "policy_version"),
        Index("idx_stability", "stability_score"),
    )


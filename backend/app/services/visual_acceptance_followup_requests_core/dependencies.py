"""Shared imports for visual acceptance follow-up helpers."""

try:
    from app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from app.services.artifact_review_followup_contract import (
        FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )
    from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
except ImportError:
    from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from backend.app.services.artifact_review_followup_contract import (
        FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )
    from backend.app.services.stores.postgres.artifacts_store import (
        PostgresArtifactsStore,
    )

__all__ = [
    "Artifact",
    "ArtifactType",
    "PrimaryActionType",
    "PostgresArtifactsStore",
    "FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF",
    "normalize_followup_action_id",
    "normalize_followup_consumer_kind",
    "normalize_followup_lane_id",
]

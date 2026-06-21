"""External dependencies for visual acceptance bundle seams."""

try:
    from app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from app.services.artifact_review_decision import (
        build_followup_action_plan,
        build_review_checklist_template,
        normalize_review_checklist_scores,
    )
    from app.services.artifact_review_followup_contract import (
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
    )
    from app.services.visual_acceptance_followup_requests import (
        materialize_followup_request_artifacts,
    )
    from app.services.visual_acceptance_owner_contract import (
        resolve_explicit_owner_capability_code,
    )
    from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
except ImportError:
    from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from backend.app.services.artifact_review_decision import (
        build_followup_action_plan,
        build_review_checklist_template,
        normalize_review_checklist_scores,
    )
    from backend.app.services.artifact_review_followup_contract import (
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
    )
    from backend.app.services.visual_acceptance_followup_requests import (
        materialize_followup_request_artifacts,
    )
    from backend.app.services.visual_acceptance_owner_contract import (
        resolve_explicit_owner_capability_code,
    )
    from backend.app.services.stores.postgres.artifacts_store import (
        PostgresArtifactsStore,
    )


"""
Artifact API routes.

RESTful API for managing playbook output artifacts.
"""

from .artifacts_core.creation import create_artifact_from_request
from .artifacts_core.detail_routes import create_artifact, get_artifact
from .artifacts_core.file_routes import get_artifact_file
from .artifacts_core.followup_routes import (
    create_artifact_review_decision,
    dispatch_artifact_followup,
    update_artifact_followup_request_state,
)
from .artifacts_core.list_routes import list_artifacts
from .artifacts_core.router import router
from .artifacts_core.schemas import (
    ArtifactResponse,
    CreateArtifactRequest,
    CreateArtifactReviewDecisionRequest,
    DispatchArtifactFollowupRequest,
    ListArtifactsResponse,
    UpdateArtifactFollowupRequestStateRequest,
)
from .artifacts_core.serializers import _generate_content_preview, artifact_to_response
from .artifacts_core.state import _utc_now, logger, store

__all__ = [
    "ArtifactResponse",
    "CreateArtifactRequest",
    "CreateArtifactReviewDecisionRequest",
    "DispatchArtifactFollowupRequest",
    "ListArtifactsResponse",
    "UpdateArtifactFollowupRequestStateRequest",
    "_generate_content_preview",
    "_utc_now",
    "artifact_to_response",
    "create_artifact",
    "create_artifact_from_request",
    "create_artifact_review_decision",
    "dispatch_artifact_followup",
    "get_artifact",
    "get_artifact_file",
    "list_artifacts",
    "logger",
    "router",
    "store",
    "update_artifact_followup_request_state",
]

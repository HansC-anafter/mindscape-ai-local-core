"""
Materialize review follow-up lanes into durable workspace artifacts.
"""

from __future__ import annotations

from .visual_acceptance_followup_requests_core.artifacts import (
    get_visual_acceptance_artifacts_store,
    _dispatch_metadata,
    _list_workspace_artifacts,
    _scene_review_metadata,
    _upsert_dispatch_artifact,
    _upsert_request_artifact,
    _upsert_scene_review_artifact,
)
from .visual_acceptance_followup_requests_core.constants import (
    FOLLOWUP_REQUEST_STATE_BLOCKED,
    FOLLOWUP_REQUEST_STATE_COMPLETED,
    FOLLOWUP_REQUEST_STATE_DISPATCHED,
    FOLLOWUP_REQUEST_STATE_READY,
    FOLLOWUP_REQUEST_STATE_SUPERSEDED,
    VALID_FOLLOWUP_REQUEST_STATES,
    VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
    VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
    VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_PLAYBOOK_CODE,
    VISUAL_ACCEPTANCE_FOLLOWUP_PLAYBOOK_CODE,
    VISUAL_ACCEPTANCE_SCENE_REVIEW_ARTIFACT_KIND,
    VISUAL_ACCEPTANCE_SCENE_REVIEW_PLAYBOOK_CODE,
    _MAX_ARTIFACT_ID_LENGTH,
)
from .visual_acceptance_followup_requests_core.dependencies import (
    Artifact,
    ArtifactType,
    FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
    PostgresArtifactsStore,
    PrimaryActionType,
    normalize_followup_action_id,
    normalize_followup_consumer_kind,
    normalize_followup_lane_id,
)
from .visual_acceptance_followup_requests_core.dispatch import (
    dispatch_followup_request,
)
from .visual_acceptance_followup_requests_core.dispatch_payloads import (
    _build_local_scene_review_request,
    _build_single_scene_storyboard,
    _bundle_content_from_request,
    _capability_owned_consumer_handoff_result,
    _dispatch_context_from_request,
    _dispatch_payload,
    _project_id_from_request,
    _scene_payload_from_request,
    _source_metadata_from_request,
    _source_type_from_request,
)
from .visual_acceptance_followup_requests_core.identifiers import (
    _bounded_execution_id,
    _bounded_identifier,
    _dispatch_artifact_id,
    _request_artifact_id,
    _safe_segment,
    _scene_review_artifact_id,
    _utc_now_iso,
)
from .visual_acceptance_followup_requests_core.laf_payloads import (
    _build_laf_patch_request,
    _laf_selection_mode,
    _laf_usage_bindings,
)
from .visual_acceptance_followup_requests_core.lifecycle import (
    materialize_followup_request_artifacts,
    persist_followup_request_state,
)
from .visual_acceptance_followup_requests_core.request_payloads import (
    _request_metadata,
    _request_payload,
)
from .visual_acceptance_followup_requests_core.state_sync import (
    _state_counts,
    _sync_followup_request_state_to_bundle,
    _sync_followup_request_state_to_run,
    _write_bundle_manifest,
)

__all__ = [
    "Artifact",
    "ArtifactType",
    "PrimaryActionType",
    "PostgresArtifactsStore",
    "FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF",
    "FOLLOWUP_REQUEST_STATE_READY",
    "FOLLOWUP_REQUEST_STATE_BLOCKED",
    "FOLLOWUP_REQUEST_STATE_DISPATCHED",
    "FOLLOWUP_REQUEST_STATE_COMPLETED",
    "FOLLOWUP_REQUEST_STATE_SUPERSEDED",
    "VALID_FOLLOWUP_REQUEST_STATES",
    "VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND",
    "VISUAL_ACCEPTANCE_FOLLOWUP_PLAYBOOK_CODE",
    "VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND",
    "VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_PLAYBOOK_CODE",
    "VISUAL_ACCEPTANCE_SCENE_REVIEW_ARTIFACT_KIND",
    "VISUAL_ACCEPTANCE_SCENE_REVIEW_PLAYBOOK_CODE",
    "get_visual_acceptance_artifacts_store",
    "materialize_followup_request_artifacts",
    "persist_followup_request_state",
    "dispatch_followup_request",
]

"""Runtime and metadata helper mixin for MeetingEngineRunner."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.services.orchestration.meeting.meeting_engine_runner_core.artifact_helpers import (
    _as_dict,
)


class MeetingEngineRunnerRuntimeMetadataMixin:
    async def _resolve_runtime_profile(self, workspace: Any) -> Optional[Any]:
        from backend.app.services.stores.workspace_runtime_profile_store import (
            WorkspaceRuntimeProfileStore,
        )

        workspace_id = getattr(workspace, "id", None)
        if not workspace_id:
            return None
        store = WorkspaceRuntimeProfileStore()
        runtime_profile = await store.get_runtime_profile(workspace_id)
        if runtime_profile is None:
            runtime_profile = await store.create_default_profile(workspace_id)
        if hasattr(runtime_profile, "ensure_phase2_fields"):
            runtime_profile.ensure_phase2_fields()
        return runtime_profile

    @staticmethod
    def _resolve_model_name(runtime_profile: Any, session: Any) -> Optional[str]:
        session_metadata = getattr(session, "metadata", None) or {}
        for value in (
            session_metadata.get("model_name"),
            getattr(runtime_profile, "model_name", None),
            getattr(runtime_profile, "default_model", None),
        ):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _request_contract_aol_metadata(session: Any) -> Dict[str, Any]:
        metadata = getattr(session, "metadata", None) or {}
        request_contract = metadata.get("request_contract")
        if not isinstance(request_contract, dict):
            return {}
        return _as_dict(request_contract.get("addressable_object_layer"))

    def _missing_dependency_result(
        self,
        *,
        session: Any,
        dependency: str,
        message: str,
    ) -> dict:
        return {
            "status": "failed",
            "session_id": getattr(session, "id", None),
            "task_ir_id": None,
            "event_ids": [],
            "minutes_md": "",
            "completion_status": "failed",
            "dispatch_result": None,
            "task_ir_artifacts": [],
            "artifact_ids": [],
            "artifact_file_paths": [],
            "artifact_db_ids": [],
            "artifact_db_errors": [],
            "artifact_landing_status": "failed",
            "producer_eval_summaries": [],
            "review_state": None,
            "review_reason": None,
            "recommended_actions": [],
            "request_contract_aol_metadata": self._request_contract_aol_metadata(session),
            "request_contract_aol_metadata_persisted": False,
            "missing_dependency": dependency,
            "error": message,
        }

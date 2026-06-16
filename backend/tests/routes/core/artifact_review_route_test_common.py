from pathlib import Path
import importlib
import json
import sys
from types import SimpleNamespace

from fastapi import FastAPI
import httpx

LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.app.capabilities.multi_media_studio.models import production_run
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services import mindscape_store, visual_acceptance_followup_requests


class _FakeArtifactsStore:
    def __init__(self):
        self.artifacts: dict[str, Artifact] = {}

    def get_artifact(self, artifact_id: str):
        return self.artifacts.get(artifact_id)

    def create_artifact(self, artifact: Artifact):
        self.artifacts[artifact.id] = artifact
        return artifact

    def update_artifact(self, artifact_id: str, **kwargs):
        artifact = self.artifacts[artifact_id]
        self.artifacts[artifact_id] = artifact.model_copy(update=kwargs)
        return True

    def list_artifacts_by_workspace(self, workspace_id: str, limit=None, offset: int = 0):
        return [
            artifact
            for artifact in self.artifacts.values()
            if str(artifact.workspace_id or "").strip() == workspace_id
        ]

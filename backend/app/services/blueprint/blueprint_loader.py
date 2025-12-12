"""
Blueprint Loader Service

Loads and applies workspace blueprints that include:
- Workspace configuration
- Recommended playbooks (by ID, not file copy)
- Initial artifacts
- Capability configurations
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from backend.app.models.workspace import Workspace, WorkspaceType
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class BlueprintInfo(BaseModel):
    """Blueprint metadata"""
    blueprint_id: str = Field(..., description="Blueprint identifier")
    title: str = Field(..., description="Blueprint display title")
    description: str = Field(..., description="Blueprint description")
    version: str = Field(..., description="Blueprint version")
    workspace_type: Optional[str] = Field(None, description="Workspace type this blueprint creates")


class BlueprintLoadResult(BaseModel):
    """Result of loading a blueprint"""
    workspace_id: str = Field(..., description="Created workspace ID")
    blueprint_id: str = Field(..., description="Blueprint ID that was loaded")
    artifacts_created: int = Field(0, description="Number of artifacts created")
    playbooks_recommended: List[str] = Field(default_factory=list, description="Recommended playbook IDs")


class BlueprintLoader:
    """
    Blueprint Loader Service

    Loads workspace blueprints from blueprints/ directory and applies them to create
    configured workspaces with recommended playbooks and initial artifacts.
    """

    def __init__(self, store: MindscapeStore, workspace_root: Optional[Path] = None):
        """
        Initialize BlueprintLoader

        Args:
            store: MindscapeStore instance
            workspace_root: Workspace root path (defaults to project root)
        """
        self.store = store
        if workspace_root is None:
            # Default to project root (parent of backend/)
            current_file = Path(__file__)
            workspace_root = current_file.parent.parent.parent.parent.parent
        self.workspace_root = workspace_root
        self.blueprints_dir = workspace_root / "blueprints"

    def list_blueprints(self) -> List[BlueprintInfo]:
        """
        List all available blueprints

        Returns:
            List of BlueprintInfo objects
        """
        blueprints = []
        if not self.blueprints_dir.exists():
            logger.warning(f"Blueprints directory not found: {self.blueprints_dir}")
            return blueprints

        for blueprint_dir in self.blueprints_dir.iterdir():
            if not blueprint_dir.is_dir():
                continue

            playbooks_json = blueprint_dir / "playbooks.json"
            if not playbooks_json.exists():
                logger.warning(f"Blueprint {blueprint_dir.name} missing playbooks.json")
                continue

            try:
                with open(playbooks_json, 'r', encoding='utf-8') as f:
                    playbooks_data = json.load(f)

                blueprint_info = BlueprintInfo(
                    blueprint_id=playbooks_data.get("blueprint_id", blueprint_dir.name),
                    title=playbooks_data.get("title", blueprint_dir.name),
                    description=playbooks_data.get("description", ""),
                    version=playbooks_data.get("version", "1.0.0"),
                    workspace_type=playbooks_data.get("workspace_type")
                )
                blueprints.append(blueprint_info)
            except Exception as e:
                logger.error(f"Failed to load blueprint info from {blueprint_dir}: {e}", exc_info=True)

        return blueprints

    def get_blueprint_info(self, blueprint_id: str) -> Optional[BlueprintInfo]:
        """
        Get blueprint information

        Args:
            blueprint_id: Blueprint identifier

        Returns:
            BlueprintInfo or None if not found
        """
        blueprints = self.list_blueprints()
        for bp in blueprints:
            if bp.blueprint_id == blueprint_id:
                return bp
        return None

    def load_blueprint(
        self,
        blueprint_id: str,
        owner_user_id: str,
        workspace_title: Optional[str] = None,
        workspace_description: Optional[str] = None
    ) -> BlueprintLoadResult:
        """
        Load a blueprint and create a workspace

        Args:
            blueprint_id: Blueprint identifier
            owner_user_id: Owner user ID for the workspace
            workspace_title: Optional workspace title (defaults to blueprint title)
            workspace_description: Optional workspace description

        Returns:
            BlueprintLoadResult with created workspace and artifacts info

        Raises:
            ValueError: If blueprint not found or invalid
        """
        blueprint_dir = self.blueprints_dir / blueprint_id
        if not blueprint_dir.exists():
            raise ValueError(f"Blueprint not found: {blueprint_id}")

        # Load blueprint configuration
        playbooks_json = blueprint_dir / "playbooks.json"
        if not playbooks_json.exists():
            raise ValueError(f"Blueprint {blueprint_id} missing playbooks.json")

        with open(playbooks_json, 'r', encoding='utf-8') as f:
            playbooks_data = json.load(f)

        workspace_json = blueprint_dir / "workspace.json"
        workspace_config = {}
        if workspace_json.exists():
            with open(workspace_json, 'r', encoding='utf-8') as f:
                workspace_config = json.load(f)

        # Determine workspace type
        workspace_type_str = playbooks_data.get("workspace_type") or workspace_config.get("workspace_type", "personal")
        try:
            workspace_type = WorkspaceType(workspace_type_str)
        except ValueError:
            logger.warning(f"Invalid workspace_type {workspace_type_str}, defaulting to personal")
            workspace_type = WorkspaceType.PERSONAL

        # Create workspace
        workspace = Workspace(
            id=str(uuid.uuid4()),
            title=workspace_title or playbooks_data.get("title", blueprint_id),
            description=workspace_description or playbooks_data.get("description", ""),
            workspace_type=workspace_type,
            owner_user_id=owner_user_id,
            primary_project_id=workspace_config.get("primary_project_id"),
            default_playbook_id=workspace_config.get("default_playbook_id"),
            default_locale=workspace_config.get("default_locale", "zh-TW"),
            mode=workspace_config.get("mode"),
            data_sources=workspace_config.get("data_sources"),
            playbook_auto_execution_config=workspace_config.get("playbook_auto_execution_config"),
            execution_mode=workspace_config.get("execution_mode", "qa"),
            expected_artifacts=workspace_config.get("expected_artifacts"),
            execution_priority=workspace_config.get("execution_priority", "medium"),
            metadata=workspace_config.get("metadata", {}),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        created_workspace = self.store.workspaces.create_workspace(workspace)
        logger.info(f"Created workspace {created_workspace.id} from blueprint {blueprint_id}")

        # Load initial artifacts
        artifacts_created = self._load_artifacts(blueprint_dir, created_workspace.id)

        # Get recommended playbooks
        recommended_playbooks = playbooks_data.get("playbooks", [])

        return BlueprintLoadResult(
            workspace_id=created_workspace.id,
            blueprint_id=blueprint_id,
            artifacts_created=artifacts_created,
            playbooks_recommended=recommended_playbooks
        )

    def _load_artifacts(self, blueprint_dir: Path, workspace_id: str) -> int:
        """
        Load initial artifacts from blueprint artifacts/ directory

        Args:
            blueprint_dir: Blueprint directory path
            workspace_id: Workspace ID to create artifacts in

        Returns:
            Number of artifacts created
        """
        artifacts_dir = blueprint_dir / "artifacts"
        if not artifacts_dir.exists():
            return 0

        artifacts_created = 0
        for artifact_file in artifacts_dir.glob("*.md"):
            try:
                with open(artifact_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse front matter if present
                metadata = {}
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        # Parse YAML front matter (simplified)
                        front_matter = parts[1].strip()
                        for line in front_matter.split("\n"):
                            if ":" in line:
                                key, value = line.split(":", 1)
                                metadata[key.strip()] = value.strip().strip('"').strip("'")
                        content = parts[2].strip()

                # Determine artifact kind from metadata or filename
                kind = metadata.get("kind", artifact_file.stem)
                title = metadata.get("title", artifact_file.stem.replace("_", " ").title())
                summary = metadata.get("summary", content[:200] if len(content) > 200 else content)

                artifact = Artifact(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    playbook_code="blueprint_init",
                    artifact_type=ArtifactType.DRAFT,
                    title=title,
                    summary=summary,
                    content={"markdown": content},
                    primary_action_type=PrimaryActionType.EDIT,
                    metadata={"kind": kind, **metadata},
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )

                self.store.artifacts.create_artifact(artifact)
                artifacts_created += 1
                logger.info(f"Created artifact {artifact.id} ({kind}) from blueprint")
            except Exception as e:
                logger.error(f"Failed to load artifact from {artifact_file}: {e}", exc_info=True)

        return artifacts_created

"""
Playbook Output Artifact Creator

Handles creation of artifacts from playbook output_artifacts definitions.
Supports template variable resolution and metadata extraction.
"""

import logging
import re
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.stores.artifacts_store import ArtifactsStore

logger = logging.getLogger(__name__)


def resolve_template(template: str, context: Dict[str, Any]) -> str:
    """
    Resolve template variables in string

    Supports variables in format: {{variable.path}}
    - {{step.step_id.output_key}} - Step outputs
    - {{input.input_key}} - Input parameters
    - {{execution_id}} - Execution ID
    - {{workspace_id}} - Workspace ID
    - {{intent_id}} - Intent ID

    Args:
        template: Template string with variables
        context: Context dictionary with step, input, execution_id, etc.

    Returns:
        Resolved string
    """
    if not template:
        return ""

    def replace_var(match):
        var_path = match.group(1).strip()
        parts = var_path.split('.')

        # Handle special variables
        if parts[0] == 'execution_id':
            return str(context.get('execution_id', ''))
        elif parts[0] == 'workspace_id':
            return str(context.get('workspace_id', ''))
        elif parts[0] == 'intent_id':
            return str(context.get('intent_id', ''))
        elif parts[0] == 'step':
            # {{step.step_id.output_key}}
            if len(parts) >= 3:
                step_id = parts[1]
                output_key = '.'.join(parts[2:])
                step_outputs = context.get('step', {})
                if step_id in step_outputs:
                    value = get_nested_value(step_outputs[step_id], output_key)
                    return str(value) if value is not None else ''
        elif parts[0] == 'input':
            # {{input.input_key}}
            if len(parts) >= 2:
                input_key = '.'.join(parts[1:])
                inputs = context.get('input', {})
                value = get_nested_value(inputs, input_key)
                return str(value) if value is not None else ''

        return match.group(0)  # Return original if not found

    # Match {{variable.path}} pattern
    pattern = r'\{\{([^}]+)\}\}'
    result = re.sub(pattern, replace_var, template)
    return result


def get_nested_value(data: Any, path: str) -> Any:
    """
    Get nested value from dictionary using dot notation

    Args:
        data: Dictionary or nested structure
        path: Dot-separated path (e.g., "step_id.output_key.sub_key")

    Returns:
        Value at path or None if not found
    """
    if not path or not data:
        return None

    parts = path.split('.')
    current = data

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                index = int(part)
                if 0 <= index < len(current):
                    current = current[index]
                else:
                    return None
            except (ValueError, TypeError):
                return None
        else:
            return None

        if current is None:
            return None

    return current


class PlaybookOutputArtifactCreator:
    """Creates artifacts from playbook output_artifacts definitions"""

    def __init__(self, artifacts_store: ArtifactsStore):
        """
        Initialize creator

        Args:
            artifacts_store: ArtifactsStore instance
        """
        self.artifacts_store = artifacts_store

    async def create_artifacts_from_playbook_outputs(
        self,
        playbook_code: str,
        execution_id: str,
        workspace_id: str,
        playbook_metadata: Dict[str, Any],
        step_outputs: Dict[str, Any],
        inputs: Dict[str, Any],
        execution_context: Optional[Dict[str, Any]] = None
    ) -> List[Artifact]:
        """
        Create artifacts from playbook output_artifacts definitions

        Args:
            playbook_code: Playbook code
            execution_id: Execution ID
            workspace_id: Workspace ID
            playbook_metadata: Playbook metadata (contains output_artifacts)
            step_outputs: All step outputs (dict of step_id -> outputs)
            inputs: Playbook inputs
            execution_context: Additional execution context

        Returns:
            List of created artifacts
        """
        output_artifacts = playbook_metadata.get("output_artifacts", [])

        if not output_artifacts:
            logger.debug(f"No output_artifacts defined for playbook {playbook_code}")
            return []

        created_artifacts = []

        # Build context for template resolution
        context = {
            "step": step_outputs,
            "input": inputs,
            "execution_id": execution_id,
            "workspace_id": workspace_id,
            "intent_id": execution_context.get("intent_id") if execution_context else None
        }

        for artifact_def in output_artifacts:
            try:
                artifact = await self._create_single_artifact(
                    playbook_code=playbook_code,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    artifact_def=artifact_def,
                    context=context,
                    execution_context=execution_context
                )

                if artifact:
                    created_artifacts.append(artifact)
                    logger.info(
                        f"Created artifact {artifact.id} from playbook {playbook_code} "
                        f"(type: {artifact.artifact_type.value}, title: {artifact.title})"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to create artifact from definition {artifact_def.get('id', 'unknown')}: {e}",
                    exc_info=True
                )
                # Continue with other artifacts even if one fails
                continue

        return created_artifacts

    async def _create_single_artifact(
        self,
        playbook_code: str,
        execution_id: str,
        workspace_id: str,
        artifact_def: Dict[str, Any],
        context: Dict[str, Any],
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Artifact]:
        """
        Create a single artifact from definition

        Args:
            playbook_code: Playbook code
            execution_id: Execution ID
            workspace_id: Workspace ID
            artifact_def: Artifact definition from output_artifacts
            context: Template resolution context
            execution_context: Additional execution context

        Returns:
            Created Artifact or None if creation failed
        """
        # Resolve title template
        title_template = artifact_def.get("title_template", "")
        if not title_template:
            logger.warning(f"Artifact definition {artifact_def.get('id')} missing title_template")
            return None

        title = resolve_template(title_template, context)

        # Resolve summary template (optional)
        summary_template = artifact_def.get("summary_template", "")
        summary = resolve_template(summary_template, context) if summary_template else ""

        # Get source data
        source_path = artifact_def.get("source", "")
        if not source_path:
            logger.warning(f"Artifact definition {artifact_def.get('id')} missing source")
            return None

        # Extract step_id and output_key from source (e.g., "step.generate_post.post_content")
        source_parts = source_path.split('.', 2)  # Split into ['step', 'step_id', 'output_key...']
        if len(source_parts) < 3 or source_parts[0] != 'step':
            logger.warning(f"Invalid source path format: {source_path}")
            return None

        step_id = source_parts[1]
        output_key = source_parts[2] if len(source_parts) > 2 else None

        # Get source data from step outputs
        step_outputs = context.get("step", {})
        if step_id not in step_outputs:
            logger.warning(f"Step {step_id} not found in step outputs")
            return None

        if output_key:
            source_data = get_nested_value(step_outputs[step_id], output_key)
        else:
            source_data = step_outputs[step_id]

        if source_data is None:
            logger.warning(f"Source data not found for {source_path}")
            return None

        # Resolve metadata
        metadata = {}
        metadata_def = artifact_def.get("metadata", {})
        if metadata_def:
            for key, value in metadata_def.items():
                if isinstance(value, str) and "{{" in value:
                    # Resolve template in metadata value
                    resolved_value = resolve_template(value, context)
                    metadata[key] = resolved_value
                elif isinstance(value, (dict, list)):
                    # Recursively resolve templates in nested structures
                    metadata[key] = self._resolve_metadata_recursive(value, context)
                else:
                    metadata[key] = value

        # Get artifact type and primary action type
        try:
            artifact_type = ArtifactType(artifact_def["artifact_type"])
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid artifact_type: {artifact_def.get('artifact_type')}, {e}")
            return None

        try:
            primary_action_type = PrimaryActionType(artifact_def["primary_action_type"])
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid primary_action_type: {artifact_def.get('primary_action_type')}, {e}")
            return None

        # Create artifact
        artifact = Artifact(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            intent_id=execution_context.get("intent_id") if execution_context else None,
            task_id=execution_context.get("task_id") if execution_context else None,
            execution_id=execution_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
            primary_action_type=primary_action_type,
            title=title,
            summary=summary,
            content=source_data if isinstance(source_data, dict) else {"content": source_data},
            storage_ref=metadata.get("file_path") or metadata.get("external_url") or metadata.get("post_url"),
            sync_state=None,
            metadata=metadata,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Save to store
        self.artifacts_store.create_artifact(artifact)

        # Automatically write file to workspace storage if file_write is enabled
        file_write_config = artifact_def.get("file_write", {})
        if file_write_config.get("enabled", False):
            try:
                await self._write_artifact_to_file(
                    artifact=artifact,
                    artifact_def=artifact_def,
                    context=context,
                    workspace_id=workspace_id,
                    playbook_metadata=playbook_metadata
                )
            except Exception as e:
                logger.error(
                    f"Failed to write artifact {artifact.id} to file: {e}",
                    exc_info=True
                )
                # Don't fail artifact creation if file write fails

        return artifact

    async def _write_artifact_to_file(
        self,
        artifact: Artifact,
        artifact_def: Dict[str, Any],
        context: Dict[str, Any],
        workspace_id: str,
        playbook_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Write artifact content to file system using three-layer architecture

        Architecture:
        1. Data Source: File system itself (workspace storage_base_path or shared storage)
        2. Shared Logical Resource: Playbook template artifacts (based on playbook scope)
        3. Workspace Overlay: Workspace-specific path overrides

        Args:
            artifact: Created artifact
            artifact_def: Artifact definition from output_artifacts
            context: Template resolution context
            workspace_id: Workspace ID
            playbook_metadata: Playbook metadata (contains scope information)
        """
        file_write_config = artifact_def.get("file_write", {})
        playbook_metadata = playbook_metadata or {}

        # Determine playbook scope
        playbook_scope_config = playbook_metadata.get("scope", {})
        if isinstance(playbook_scope_config, dict):
            playbook_scope = playbook_scope_config.get("visibility", "workspace")
        else:
            playbook_scope = "workspace"

        # Resolve storage path based on three-layer architecture
        storage_info = self._resolve_storage_path(
            playbook_code=playbook_metadata.get("playbook_code", ""),
            playbook_scope=playbook_scope,
            execution_id=context.get("execution_id", ""),
            artifact_file_name=artifact_def.get("file_name_template", "{{title}}.tsx"),
            workspace_id=workspace_id,
            context=context
        )

        if not storage_info:
            logger.warning(f"Failed to resolve storage path for artifact {artifact.id}, skipping file write")
            return

        base_directory = storage_info["base_directory"]
        relative_file_path = storage_info["relative_path"]

        # Build file content
        content_template = file_write_config.get("content_template")
        if content_template:
            file_content = resolve_template(content_template, context)
        else:
            source_data = artifact.content
            if isinstance(source_data, dict):
                file_content = source_data.get("content") or source_data.get("code") or str(source_data)
            else:
                file_content = str(source_data)

        # Get encoding
        encoding = file_write_config.get("encoding", "utf-8")

        # Register filesystem tool instance for this base_directory if not already registered
        # This follows the three-layer architecture: different scopes get different tool instances
        tool_id = self._get_or_register_filesystem_tool(base_directory, playbook_scope, workspace_id)

        if not tool_id:
            logger.warning(f"Failed to register filesystem tool for {base_directory}, writing directly")
            # Fallback: write directly
            full_file_path = base_directory / relative_file_path
            full_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_file_path, "w", encoding=encoding) as f:
                f.write(file_content)
            result = {"success": True, "file_path": str(full_file_path)}
        else:
            # Use registered tool instance
            from backend.app.shared.tool_executor import execute_tool
            result = await execute_tool(
                tool_id,
                file_path=relative_file_path,
                content=file_content,
                encoding=encoding
            )

            logger.info(
                f"Successfully wrote artifact {artifact.id} to file: {base_directory}/{relative_file_path} "
                f"(size: {len(file_content)} bytes, scope: {playbook_scope})"
            )

            # Update artifact metadata with actual file path
            full_path = base_directory / relative_file_path
            artifact.metadata["actual_file_path"] = str(full_path)
            artifact.metadata["storage_scope"] = playbook_scope
            artifact.storage_ref = str(full_path)
            self.artifacts_store.update_artifact(
                artifact.id,
                metadata=artifact.metadata,
                storage_ref=str(full_path)
            )
        except Exception as e:
            logger.error(f"Failed to write artifact file: {e}", exc_info=True)
            raise

    def _resolve_storage_path(
        self,
        playbook_code: str,
        playbook_scope: str,
        execution_id: str,
        artifact_file_name: str,
        workspace_id: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve artifact storage path based on three-layer architecture

        Returns:
            Dict with "base_directory" and "relative_path", or None if resolution fails
        """
        from backend.app.services.mindscape_store import MindscapeStore
        from pathlib import Path
        import os

        store = MindscapeStore()
        workspace = store.get_workspace(workspace_id)

        if not workspace:
            logger.warning(f"Workspace {workspace_id} not found")
            return None

        # Resolve file name template
        resolved_file_name = resolve_template(artifact_file_name, context)

        if playbook_scope == "workspace":
            # Workspace-scoped: use workspace storage
            if not workspace.storage_base_path:
                logger.warning(f"Workspace {workspace_id} does not have storage_base_path configured")
                return None

            base_directory = Path(workspace.storage_base_path)
            artifacts_dir = workspace.artifacts_dir or "artifacts"
            relative_path = f"{artifacts_dir}/{playbook_code}/{execution_id}/{resolved_file_name}"

        elif playbook_scope in ("system", "tenant", "profile"):
            # Shared resource: use shared storage
            # For Phase 1, we'll use a shared storage base path
            # This should be configured via environment variable or system settings
            shared_storage_base = os.getenv(
                "SHARED_STORAGE_BASE_PATH",
                "/app/data/shared"  # Default shared storage path
            )

            # Determine scope path
            if playbook_scope == "system":
                scope_path = "system"
            elif playbook_scope == "tenant":
                tenant_id = context.get("tenant_id") or workspace.owner_user_id  # Fallback
                scope_path = f"tenant-{tenant_id}" if tenant_id else "system"
            elif playbook_scope == "profile":
                profile_id = context.get("profile_id") or workspace.owner_user_id  # Fallback
                scope_path = f"profile-{profile_id}" if profile_id else "system"
            else:
                scope_path = "system"

            base_directory = Path(shared_storage_base) / scope_path / "playbooks" / playbook_code / "artifacts"
            relative_path = f"{execution_id}/{resolved_file_name}"

        else:
            # Fallback to workspace storage for unknown scope
            logger.warning(f"Unknown playbook scope: {playbook_scope}, falling back to workspace storage")
            if not workspace.storage_base_path:
                return None

            base_directory = Path(workspace.storage_base_path)
            artifacts_dir = workspace.artifacts_dir or "artifacts"
            relative_path = f"{artifacts_dir}/{playbook_code}/{execution_id}/{resolved_file_name}"

        # Ensure base directory exists
        base_directory.mkdir(parents=True, exist_ok=True)

        return {
            "base_directory": base_directory,
            "relative_path": relative_path
        }

    def _get_or_register_filesystem_tool(
        self,
        base_directory: Path,
        playbook_scope: str,
        workspace_id: str
    ) -> Optional[str]:
        """
        Get or register filesystem_write_file tool instance for the given base_directory

        This implements scheme 3: register different tool instances for different scopes

        Args:
            base_directory: Base directory path for the tool
            playbook_scope: Playbook scope (system/tenant/profile/workspace)
            workspace_id: Workspace ID (for workspace-scoped tools)

        Returns:
            Tool ID for the registered tool instance, or None if registration fails
        """
        from backend.app.services.tools.local_filesystem.filesystem_tools import FilesystemWriteFileTool
        from backend.app.services.tools.registry import register_mindscape_tool

        # Generate tool ID based on scope and base directory
        # Format: filesystem_write_{scope}_{identifier}
        if playbook_scope == "workspace":
            identifier = f"workspace_{workspace_id}"
        elif playbook_scope == "system":
            identifier = "system"
        elif playbook_scope == "tenant":
            # Extract tenant ID from base_directory path if possible
            identifier = base_directory.parts[-3] if len(base_directory.parts) >= 3 else "tenant"
        elif playbook_scope == "profile":
            # Extract profile ID from base_directory path if possible
            identifier = base_directory.parts[-3] if len(base_directory.parts) >= 3 else "profile"
        else:
            identifier = "default"

        tool_id = f"filesystem_write_{identifier}"

        # Check if tool is already registered
        try:
            from backend.app.services.tools.registry import get_mindscape_tool
            existing_tool = get_mindscape_tool(tool_id)
            if existing_tool:
                logger.debug(f"Filesystem tool {tool_id} already registered")
                return tool_id
        except Exception:
            pass

        # Register new tool instance
        try:
            tool_instance = FilesystemWriteFileTool(base_directory=str(base_directory))
            register_mindscape_tool(tool_id, tool_instance)
            logger.info(f"Registered filesystem tool {tool_id} for base_directory: {base_directory}")
            return tool_id
        except Exception as e:
            logger.error(f"Failed to register filesystem tool {tool_id}: {e}", exc_info=True)
            return None

    def _resolve_metadata_recursive(self, value: Any, context: Dict[str, Any]) -> Any:
        """
        Recursively resolve templates in metadata values

        Args:
            value: Value to resolve (can be dict, list, or string)
            context: Template resolution context

        Returns:
            Resolved value
        """
        if isinstance(value, dict):
            return {k: self._resolve_metadata_recursive(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_metadata_recursive(item, context) for item in value]
        elif isinstance(value, str) and "{{" in value:
            return resolve_template(value, context)
        else:
            return value


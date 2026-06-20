"""
Playbook Output Artifact Creator

Handles creation of artifacts from playbook output_artifacts definitions.
Supports template variable resolution and metadata extraction.
"""

import logging
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.playbook_output_artifacts.file_writer import (
    get_or_register_filesystem_tool_for_creator,
    resolve_storage_path_for_creator,
    write_artifact_to_file_for_creator,
)
from backend.app.services.playbook_output_artifacts.templates import (
    _resolve_context_path,
    _serialize_artifact_file_content,
    get_nested_value,
    resolve_template,
)
from backend.app.services.stores.artifacts_store import ArtifactsStore

logger = logging.getLogger(__name__)


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
        execution_context: Optional[Dict[str, Any]] = None,
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
            "intent_id": (
                execution_context.get("intent_id") if execution_context else None
            ),
        }

        logger.debug(
            f"create_artifacts_from_playbook_outputs: execution_context={execution_context}, sandbox_id={execution_context.get('sandbox_id') if execution_context else None}"
        )
        for artifact_def in output_artifacts:
            try:
                fan_out_source = str(artifact_def.get("fan_out_source") or "").strip()
                fan_out_items = None
                if fan_out_source:
                    fan_out_items = _resolve_context_path(context, fan_out_source)
                    if not isinstance(fan_out_items, list):
                        logger.warning(
                            f"Artifact definition {artifact_def.get('id')} fan_out_source "
                            f"did not resolve to a list: {fan_out_source}"
                        )
                        continue

                iterable_items = fan_out_items if fan_out_items is not None else [None]
                for item_index, item in enumerate(iterable_items):
                    item_context = context
                    if fan_out_items is not None:
                        item_context = {
                            **context,
                            "item": item,
                            "item_index": item_index,
                        }

                    artifact = await self._create_single_artifact(
                        playbook_code=playbook_code,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        artifact_def=artifact_def,
                        context=item_context,
                        execution_context=execution_context,
                        playbook_metadata=playbook_metadata,
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
                    exc_info=True,
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
        execution_context: Optional[Dict[str, Any]] = None,
        playbook_metadata: Optional[Dict[str, Any]] = None,
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
            logger.warning(
                f"Artifact definition {artifact_def.get('id')} missing title_template"
            )
            return None

        title = resolve_template(title_template, context)

        # Resolve summary template (optional)
        summary_template = artifact_def.get("summary_template", "")
        summary = (
            resolve_template(summary_template, context) if summary_template else ""
        )

        # Get source data
        source_path = artifact_def.get("source", "")
        if not source_path:
            logger.warning(
                f"Artifact definition {artifact_def.get('id')} missing source"
            )
            return None

        source_data = None

        # Check if source is from sandbox (format: "sandbox.file_path")
        if source_path.startswith("sandbox."):
            # Read from sandbox
            sandbox_file_path = source_path[8:]  # Remove "sandbox." prefix
            sandbox_id = (
                execution_context.get("sandbox_id") if execution_context else None
            )

            if not sandbox_id:
                logger.warning(
                    f"Sandbox ID not found in execution context, cannot read from sandbox: {sandbox_file_path}"
                )
                return None

            try:
                from backend.app.services.sandbox.sandbox_manager import SandboxManager
                from backend.app.services.mindscape_store import MindscapeStore

                store = MindscapeStore()
                sandbox_manager = SandboxManager(store)
                sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)

                if not sandbox:
                    logger.warning(f"Sandbox {sandbox_id} not found")
                    return None

                file_content = await sandbox.read_file(sandbox_file_path)
                if not file_content:
                    logger.warning(
                        f"File {sandbox_file_path} not found in sandbox {sandbox_id}"
                    )
                    return None

                # Parse JSON content if file is JSON
                import json

                if sandbox_file_path.endswith(".json"):
                    try:
                        source_data = json.loads(file_content)
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Failed to parse JSON from sandbox file {sandbox_file_path}"
                        )
                        source_data = {"content": file_content}
                else:
                    source_data = {"content": file_content}

                logger.info(
                    f"Successfully read file {sandbox_file_path} from sandbox {sandbox_id}"
                )
            except Exception as e:
                logger.error(f"Failed to read file from sandbox: {e}", exc_info=True)
                return None
        elif source_path.startswith("step."):
            # Extract step_id and output_key from source (e.g., "step.generate_post.post_content")
            source_parts = source_path.split(
                ".", 2
            )  # ['step', 'step_id'] or ['step', 'step_id', 'output_key...']
            if len(source_parts) < 2:
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
        else:
            source_data = _resolve_context_path(context, source_path)
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
        artifact_type_value = artifact_def.get("artifact_type")
        artifact_type_from = str(artifact_def.get("artifact_type_from") or "").strip()
        if artifact_type_from:
            artifact_type_value = _resolve_context_path(context, artifact_type_from) or artifact_type_value

        primary_action_type_value = artifact_def.get("primary_action_type")
        primary_action_type_from = str(
            artifact_def.get("primary_action_type_from") or ""
        ).strip()
        if primary_action_type_from:
            primary_action_type_value = (
                _resolve_context_path(context, primary_action_type_from)
                or primary_action_type_value
            )

        try:
            artifact_type = ArtifactType(str(artifact_type_value or "").strip())
        except (KeyError, ValueError) as e:
            logger.error(
                f"Invalid artifact_type: {artifact_type_value}, {e}"
            )
            return None

        try:
            primary_action_type = PrimaryActionType(
                str(primary_action_type_value or "").strip()
            )
        except (KeyError, ValueError) as e:
            logger.error(
                f"Invalid primary_action_type: {primary_action_type_value}, {e}"
            )
            return None

        # Create artifact
        artifact = Artifact(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            intent_id=execution_context.get("intent_id") if execution_context else None,
            task_id=execution_context.get("task_id") if execution_context else None,
            execution_id=execution_id,
            thread_id=execution_context.get("thread_id") if execution_context else None,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
            primary_action_type=primary_action_type,
            title=title,
            summary=summary,
            content=(
                source_data
                if isinstance(source_data, dict)
                else {"content": source_data}
            ),
            storage_ref=metadata.get("file_path")
            or metadata.get("storage_ref")
            or metadata.get("external_url")
            or metadata.get("post_url"),
            sync_state=None,
            metadata=metadata,
            created_at=_utc_now(),
            updated_at=_utc_now(),
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
                    execution_context=execution_context,
                    playbook_metadata=playbook_metadata,
                )
            except Exception as e:
                logger.error(
                    f"Failed to write artifact {artifact.id} to file: {e}",
                    exc_info=True,
                )
                # Don't fail artifact creation if file write fails

        return artifact

    async def _write_artifact_to_file(
        self,
        artifact: Artifact,
        artifact_def: Dict[str, Any],
        context: Dict[str, Any],
        workspace_id: str,
        execution_context: Optional[Dict[str, Any]] = None,
        playbook_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        await write_artifact_to_file_for_creator(
            self,
            artifact=artifact,
            artifact_def=artifact_def,
            context=context,
            workspace_id=workspace_id,
            execution_context=execution_context,
            playbook_metadata=playbook_metadata,
        )

    async def _resolve_storage_path(
        self,
        playbook_code: str,
        playbook_scope: str,
        execution_id: str,
        artifact_file_name: str,
        workspace_id: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return await resolve_storage_path_for_creator(
            playbook_code=playbook_code,
            playbook_scope=playbook_scope,
            execution_id=execution_id,
            artifact_file_name=artifact_file_name,
            workspace_id=workspace_id,
            context=context,
        )

    def _get_or_register_filesystem_tool(
        self, base_directory: Path, playbook_scope: str, workspace_id: str
    ) -> Optional[str]:
        return get_or_register_filesystem_tool_for_creator(
            base_directory,
            playbook_scope,
            workspace_id,
        )

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
            if set(value.keys()) == {"value_from"} and isinstance(
                value.get("value_from"), str
            ):
                return get_nested_value(context, value["value_from"])
            return {
                k: self._resolve_metadata_recursive(v, context)
                for k, v in value.items()
            }
        elif isinstance(value, list):
            return [self._resolve_metadata_recursive(item, context) for item in value]
        elif isinstance(value, str) and "{{" in value:
            return resolve_template(value, context)
        else:
            return value

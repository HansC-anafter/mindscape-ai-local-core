"""File writing helpers for playbook output artifacts."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.models.workspace import Artifact
from backend.app.services.playbook_output_artifacts.templates import (
    _serialize_artifact_file_content,
    resolve_template,
)

logger = logging.getLogger(__name__)


async def write_artifact_to_file_for_creator(
    creator: Any,
    *,
    artifact: Artifact,
    artifact_def: Dict[str, Any],
    context: Dict[str, Any],
    workspace_id: str,
    execution_context: Optional[Dict[str, Any]] = None,
    playbook_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Write artifact content to a sandbox or filesystem path."""
    file_write_config = artifact_def.get("file_write", {})
    if playbook_metadata is None:
        playbook_metadata = {}

    playbook_scope_config = playbook_metadata.get("scope", {})
    if isinstance(playbook_scope_config, dict):
        playbook_scope = playbook_scope_config.get("visibility", "workspace")
    else:
        playbook_scope = "workspace"

    enhanced_context = context.copy()
    enhanced_context["artifact"] = {
        "title": artifact.title,
        "id": artifact.id,
        "type": artifact.artifact_type.value if artifact.artifact_type else "other",
    }
    enhanced_context["title"] = artifact.title

    file_name_template = file_write_config.get(
        "file_name_template", "{{title}}.tsx"
    )
    logger.info(
        f"_write_artifact_to_file: artifact.id={artifact.id}, "
        f"file_name_template='{file_name_template}', "
        f"artifact.title='{artifact.title}', "
        f"enhanced_context.artifact.title='{enhanced_context['artifact']['title']}', "
        f"enhanced_context.title='{enhanced_context.get('title')}'"
    )
    storage_info = await resolve_storage_path_for_creator(
        playbook_code=playbook_metadata.get("playbook_code", ""),
        playbook_scope=playbook_scope,
        execution_id=context.get("execution_id", ""),
        artifact_file_name=file_name_template,
        workspace_id=workspace_id,
        context=enhanced_context,
    )

    if not storage_info:
        logger.warning(
            f"Failed to resolve storage path for artifact {artifact.id}, skipping file write"
        )
        return

    base_directory = storage_info["base_directory"]
    relative_file_path = storage_info["relative_path"]

    content_template = file_write_config.get("content_template")
    if content_template:
        file_content = resolve_template(content_template, enhanced_context)
    else:
        file_content = _serialize_artifact_file_content(artifact.content)

    encoding = file_write_config.get("encoding", "utf-8")

    sandbox_id = execution_context.get("sandbox_id") if execution_context else None
    logger.debug(
        f"_write_artifact_to_file: sandbox_id={sandbox_id}, execution_context={execution_context}, artifact.id={artifact.id}"
    )
    if sandbox_id:
        logger.debug(
            f"_write_artifact_to_file: Attempting to write to sandbox {sandbox_id}"
        )
        try:
            from backend.app.services.sandbox.sandbox_manager import SandboxManager
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            sandbox_manager = SandboxManager(store)
            sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)

            if sandbox:
                logger.info(
                    f"Writing file to sandbox {sandbox_id}: {relative_file_path}"
                )
                success = await sandbox.write_file(relative_file_path, file_content)
                logger.info(f"sandbox.write_file result: success={success}")
                if success:
                    actual_file_path = await _resolve_sandbox_actual_file_path(
                        sandbox=sandbox,
                        sandbox_manager=sandbox_manager,
                        sandbox_id=sandbox_id,
                        workspace_id=workspace_id,
                        relative_file_path=relative_file_path,
                    )
                    _update_artifact_file_metadata(
                        creator,
                        artifact=artifact,
                        actual_file_path=actual_file_path,
                        playbook_scope=playbook_scope,
                    )
                    logger.info(
                        f"Successfully wrote artifact {artifact.id} to sandbox {sandbox_id}: {relative_file_path} "
                        f"(size: {len(file_content)} bytes)"
                    )
                    return
                logger.warning(
                    f"Failed to write file to sandbox {sandbox_id}, falling back to filesystem"
                )
            else:
                logger.warning(
                    f"Sandbox {sandbox_id} not found, falling back to filesystem"
                )
        except Exception as exc:
            logger.error(f"Failed to write file to sandbox: {exc}", exc_info=True)

    try:
        tool_id = get_or_register_filesystem_tool_for_creator(
            base_directory, playbook_scope, workspace_id
        )

        if not tool_id:
            logger.warning(
                f"Failed to register filesystem tool for {base_directory}, writing directly"
            )
            full_file_path = base_directory / relative_file_path
            full_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_file_path, "w", encoding=encoding) as file:
                file.write(file_content)
            _update_artifact_file_metadata(
                creator,
                artifact=artifact,
                actual_file_path=full_file_path,
                playbook_scope=playbook_scope,
            )
            logger.info(
                f"Successfully wrote artifact {artifact.id} to file (fallback): {full_file_path} "
                f"(size: {len(file_content)} bytes, scope: {playbook_scope})"
            )
        else:
            from backend.app.shared.tool_executor import execute_tool

            await execute_tool(
                tool_id,
                file_path=relative_file_path,
                content=file_content,
                encoding=encoding,
            )

            logger.info(
                f"Successfully wrote artifact {artifact.id} to file: {base_directory}/{relative_file_path} "
                f"(size: {len(file_content)} bytes, scope: {playbook_scope})"
            )
            full_path = base_directory / relative_file_path
            _update_artifact_file_metadata(
                creator,
                artifact=artifact,
                actual_file_path=full_path,
                playbook_scope=playbook_scope,
            )
    except Exception as exc:
        logger.error(f"Failed to write artifact file: {exc}", exc_info=True)
        raise


async def resolve_storage_path_for_creator(
    *,
    playbook_code: str,
    playbook_scope: str,
    execution_id: str,
    artifact_file_name: str,
    workspace_id: str,
    context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Resolve artifact storage path based on playbook scope."""
    from backend.app.services.mindscape_store import MindscapeStore

    store = MindscapeStore()
    workspace = await store.get_workspace(workspace_id)

    if not workspace:
        logger.warning(f"Workspace {workspace_id} not found")
        return None

    resolved_file_name = resolve_template(artifact_file_name, context)
    logger.info(
        f"_resolve_storage_path: artifact_file_name='{artifact_file_name}', "
        f"resolved_file_name='{resolved_file_name}', "
        f"context.artifact.title='{context.get('artifact', {}).get('title')}', "
        f"context.title='{context.get('title')}'"
    )

    if playbook_scope == "workspace":
        if not workspace.storage_base_path:
            logger.warning(
                f"Workspace {workspace_id} does not have storage_base_path configured"
            )
            return None

        base_directory = Path(workspace.storage_base_path)
        artifacts_dir = workspace.artifacts_dir or "artifacts"
        relative_path = (
            f"{artifacts_dir}/{playbook_code}/{execution_id}/{resolved_file_name}"
        )
    elif playbook_scope in ("system", "tenant", "profile"):
        shared_storage_base = os.getenv(
            "SHARED_STORAGE_BASE_PATH",
            "/app/data/shared",
        )

        if playbook_scope == "system":
            scope_path = "system"
        elif playbook_scope == "tenant":
            tenant_id = context.get("tenant_id") or workspace.owner_user_id
            scope_path = f"tenant-{tenant_id}" if tenant_id else "system"
        elif playbook_scope == "profile":
            profile_id = context.get("profile_id") or workspace.owner_user_id
            scope_path = f"profile-{profile_id}" if profile_id else "system"
        else:
            scope_path = "system"

        base_directory = (
            Path(shared_storage_base)
            / scope_path
            / "playbooks"
            / playbook_code
            / "artifacts"
        )
        relative_path = f"{execution_id}/{resolved_file_name}"
    else:
        logger.warning(
            f"Unknown playbook scope: {playbook_scope}, falling back to workspace storage"
        )
        if not workspace.storage_base_path:
            return None

        base_directory = Path(workspace.storage_base_path)
        artifacts_dir = workspace.artifacts_dir or "artifacts"
        relative_path = (
            f"{artifacts_dir}/{playbook_code}/{execution_id}/{resolved_file_name}"
        )

    base_directory.mkdir(parents=True, exist_ok=True)
    return {"base_directory": base_directory, "relative_path": relative_path}


def get_or_register_filesystem_tool_for_creator(
    base_directory: Path, playbook_scope: str, workspace_id: str
) -> Optional[str]:
    """Get or register a filesystem write tool for the given base directory."""
    from backend.app.services.tools.local_filesystem.filesystem_tools import (
        FilesystemWriteFileTool,
    )
    from backend.app.services.tools.registry import register_mindscape_tool

    if playbook_scope == "workspace":
        identifier = f"workspace_{workspace_id}"
    elif playbook_scope == "system":
        identifier = "system"
    elif playbook_scope == "tenant":
        identifier = (
            base_directory.parts[-3] if len(base_directory.parts) >= 3 else "tenant"
        )
    elif playbook_scope == "profile":
        identifier = (
            base_directory.parts[-3] if len(base_directory.parts) >= 3 else "profile"
        )
    else:
        identifier = "default"

    tool_id = f"filesystem_write_{identifier}"

    try:
        from backend.app.services.tools.registry import get_mindscape_tool

        existing_tool = get_mindscape_tool(tool_id)
        if existing_tool:
            logger.debug(f"Filesystem tool {tool_id} already registered")
            return tool_id
    except Exception:
        pass

    try:
        tool_instance = FilesystemWriteFileTool(base_directory=str(base_directory))
        register_mindscape_tool(tool_id, tool_instance)
        logger.info(
            f"Registered filesystem tool {tool_id} for base_directory: {base_directory}"
        )
        return tool_id
    except Exception as exc:
        logger.error(
            f"Failed to register filesystem tool {tool_id}: {exc}", exc_info=True
        )
        return None


async def _resolve_sandbox_actual_file_path(
    *,
    sandbox: Any,
    sandbox_manager: Any,
    sandbox_id: str,
    workspace_id: str,
    relative_file_path: str,
) -> Path:
    if hasattr(sandbox, "storage") and hasattr(sandbox.storage, "base_path"):
        sandbox_base_path = sandbox.storage.base_path / "current"
        return sandbox_base_path / relative_file_path

    try:
        sandbox_info = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if sandbox_info and hasattr(sandbox_info, "storage"):
            sandbox_base_path = sandbox_info.storage.base_path / "current"
        else:
            sandbox_base_path = await _default_sandbox_base_path(
                sandbox_id=sandbox_id,
                workspace_id=workspace_id,
            )
        return sandbox_base_path / relative_file_path
    except Exception as exc:
        logger.warning(f"Failed to get sandbox base path: {exc}, using relative path")
        return Path(relative_file_path)


async def _default_sandbox_base_path(*, sandbox_id: str, workspace_id: str) -> Path:
    from backend.app.services.mindscape_store import MindscapeStore

    store = MindscapeStore()
    workspace = await store.get_workspace(workspace_id)
    if (
        workspace
        and hasattr(workspace, "storage_base_path")
        and workspace.storage_base_path
    ):
        return (
            Path(workspace.storage_base_path)
            / "sandboxes"
            / workspace_id
            / "project_repo"
            / sandbox_id
            / "current"
        )
    return (
        Path("/app/data/sandboxes")
        / workspace_id
        / "project_repo"
        / sandbox_id
        / "current"
    )


def _update_artifact_file_metadata(
    creator: Any,
    *,
    artifact: Artifact,
    actual_file_path: Path,
    playbook_scope: str,
) -> None:
    artifact.metadata["actual_file_path"] = str(actual_file_path)
    artifact.metadata["storage_scope"] = playbook_scope
    artifact.storage_ref = str(actual_file_path)
    creator.artifacts_store.update_artifact(
        artifact.id,
        metadata=artifact.metadata,
        storage_ref=str(actual_file_path),
    )

"""Flow and playbook metadata helpers for workspace project card routes."""

import logging
from datetime import datetime
from pathlib import Path as FilePath
from typing import Any, Dict, List

from backend.app.models.playbook_flow import PlaybookFlow
from backend.app.models.project import Project
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


async def ensure_project_flow_exists(
    *,
    project: Project,
    workspace: Workspace,
    store: MindscapeStore,
    project_id: str,
) -> None:
    """Ensure flow exists, creating it only through the existing missing-flow path."""
    if not project.flow_id:
        return

    from backend.app.services.project.project_detector import ProjectDetector
    from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore

    flows_store = PlaybookFlowsStore(store.db_path)
    flow = flows_store.get_flow(project.flow_id)

    if flow:
        return

    logger.info(
        f"Flow {project.flow_id} not found for project {project_id}, creating flow with LLM analysis"
    )
    project_detector = ProjectDetector()

    # Build message for LLM analysis
    message = f"{project.title}"
    if project.type:
        message += f" (type: {project.type})"

    # Check metadata for additional context
    if project.metadata and isinstance(project.metadata, dict):
        primary_intent = project.metadata.get("primary_intent")
        if primary_intent:
            message += f"\n\nOriginal intent: {primary_intent}"

    # Get playbook_sequence suggestion from LLM
    try:
        suggestion = await project_detector.detect(
            message=message, conversation_context=[], workspace=workspace
        )

        if suggestion and suggestion.mode == "project" and suggestion.playbook_sequence:
            raw_playbook_sequence = suggestion.playbook_sequence
            logger.info(
                f"LLM suggested {len(raw_playbook_sequence)} playbooks for project {project_id}"
            )

            # Validate playbook existence before creating flow (using unified validator)
            from backend.app.services.project.playbook_validator import (
                validate_playbook_sequence,
            )

            # Adjust path for increased nesting level
            base_dir = FilePath(__file__).parent.parent.parent.parent.parent
            playbook_sequence = validate_playbook_sequence(
                raw_playbook_sequence, base_dir
            )
        else:
            playbook_sequence = []
            logger.warning(f"LLM did not suggest playbooks for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to get LLM suggestion for project {project_id}: {e}")
        playbook_sequence = []

    # Create flow with validated playbook_sequence (only existing playbooks)
    flow = PlaybookFlow(
        id=project.flow_id,
        name=(
            f"{project.type.replace('_', ' ').title()} Flow" if project.type else "Flow"
        ),
        description=(
            f"Flow for {project.type} projects" if project.type else "Default flow"
        ),
        flow_definition={
            "nodes": [],
            "edges": [],
            "playbook_sequence": playbook_sequence,
        },
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    flows_store.create_flow(flow)
    logger.info(
        f"Created flow: {project.flow_id} with {len(playbook_sequence)} validated playbooks for project {project_id}"
    )


def build_playbook_card_context(
    *,
    project: Project,
    store: MindscapeStore,
    completed_executions: List[Any],
) -> Dict[str, Any]:
    """Build playbook list and progress metadata for the project card."""
    total_playbooks = 0
    playbook_list = []
    if project.flow_id:
        from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore

        flows_store = PlaybookFlowsStore(store.db_path)
        flow = flows_store.get_flow(project.flow_id)
        if flow:
            # Get playbook_sequence from flow_definition
            flow_def = (
                flow.flow_definition if isinstance(flow.flow_definition, dict) else {}
            )
            playbook_sequence = flow_def.get("playbook_sequence", [])

            if playbook_sequence:
                # Get playbook details (playbook_sequence is already validated when flow was created)
                from backend.app.services.playbook_loaders.file_loader import (
                    PlaybookFileLoader,
                )

                total_playbooks = len(playbook_sequence)
                # Adjust Base Dir
                base_dir = FilePath(__file__).parent.parent.parent.parent.parent

                for playbook_code in playbook_sequence:
                    playbook_name = playbook_code.replace("_", " ").title()
                    playbook_description = ""

                    # Load playbook details from i18n markdown files
                    for locale in ["zh-TW", "en", "ja"]:
                        i18n_dir = base_dir / "backend" / "i18n" / "playbooks" / locale
                        md_file = i18n_dir / f"{playbook_code}.md"

                        if md_file.exists():
                            try:
                                playbook = PlaybookFileLoader.load_playbook_from_file(
                                    md_file
                                )
                                if playbook and playbook.metadata:
                                    playbook_name = (
                                        playbook.metadata.name
                                        if playbook.metadata.name
                                        else playbook_name
                                    )
                                    if not playbook_description:
                                        playbook_description = (
                                            playbook.metadata.description
                                            if playbook.metadata.description
                                            else ""
                                        )
                                    # Found valid playbook, break
                                    break
                            except Exception as e:
                                logger.debug(
                                    f"Failed to load playbook {playbook_code} from {locale} markdown: {e}"
                                )

                    playbook_list.append(
                        {
                            "code": playbook_code,
                            "name": playbook_name,
                            "description": playbook_description,
                        }
                    )
            else:
                logger.info(f"Flow {project.flow_id} has no playbook_sequence")
        else:
            logger.warning(f"Flow {project.flow_id} not found for project {project.id}")
    else:
        logger.warning(
            f"Project {project.id} has no flow_id, cannot determine playbooks"
        )

    progress_current, progress_label = _calculate_progress(
        total_playbooks=total_playbooks,
        completed_executions=completed_executions,
    )
    return {
        "total_playbooks": total_playbooks,
        "playbook_list": playbook_list,
        "progress_current": progress_current,
        "progress_label": progress_label,
    }


def _calculate_progress(
    *,
    total_playbooks: int,
    completed_executions: List[Any],
) -> tuple[int, str]:
    if total_playbooks > 0:
        # Extract playbook_code from executions (handle both dict and object formats)
        def get_playbook_code(exec_obj):
            if isinstance(exec_obj, dict):
                return exec_obj.get("playbook_code") or exec_obj.get("task", {}).get(
                    "execution_context", {}
                ).get("playbook_code")
            return (
                exec_obj.playbook_code if hasattr(exec_obj, "playbook_code") else None
            )

        completed_playbooks = len(
            set(
                [
                    get_playbook_code(e)
                    for e in completed_executions
                    if get_playbook_code(e)
                ]
            )
        )
        # Cap progress at 100% if completed exceeds total (can happen if playbooks were added after execution)
        progress_current = (
            min(100, int((completed_playbooks / total_playbooks) * 100))
            if total_playbooks > 0
            else 0
        )
        progress_label = f"{completed_playbooks}/{total_playbooks} Playbooks 完成"
        logger.info(
            f"[ProjectCard] Progress: {completed_playbooks}/{total_playbooks} playbooks completed, {progress_current}%"
        )
    else:
        progress_current = 0
        progress_label = "尚未開始"

    return progress_current, progress_label

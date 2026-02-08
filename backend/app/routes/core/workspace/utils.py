import logging
from ....services.mindscape_store import MindscapeStore
from ....services.stores.tasks_store import TasksStore
from ....models.workspace import LaunchStatus

logger = logging.getLogger(__name__)


def get_store():
    return MindscapeStore()


async def ensure_workspace_launch_status(workspace_id: str, workspace) -> str:
    """
    Ensure workspace launch_status is up-to-date based on actual content/executions.
    Automatically updates the database if a state change is detected.
    Returns the current (potentially updated) status string.
    """
    store = get_store()

    # Normalize current_status
    if hasattr(workspace.launch_status, "value"):
        current_status = workspace.launch_status.value
    else:
        current_status = (
            str(workspace.launch_status) if workspace.launch_status else "pending"
        )

    if current_status != "pending":
        return current_status

    has_usage_records = False
    has_executions = False

    # Check for execution records
    try:
        tasks_store = TasksStore(store.db_path)
        executions = tasks_store.list_executions_by_workspace(workspace_id, limit=1)
        has_executions = len(executions) > 0
    except Exception as e:
        logger.warning(f"Failed to check executions for workspace {workspace_id}: {e}")

    # Check for event records (if no executions found)
    if not has_executions:
        try:
            events = store.get_events_by_workspace(workspace_id, limit=1)
            has_usage_records = len(events) > 0
        except Exception as e:
            logger.warning(f"Failed to check events for workspace {workspace_id}: {e}")

    # Auto-update status if workspace has execution/event records
    if has_executions:
        # Has execution records -> active
        try:
            workspace.launch_status = LaunchStatus.ACTIVE
            await store.update_workspace(workspace)
            logger.info(
                f"Auto-updated workspace {workspace_id} status from pending to active (has executions)"
            )
            return "active"
        except Exception as e:
            logger.warning(f"Failed to auto-update workspace status to active: {e}")
    elif has_usage_records:
        # Has event records -> ready
        try:
            workspace.launch_status = LaunchStatus.READY
            await store.update_workspace(workspace)
            logger.info(
                f"Auto-updated workspace {workspace_id} status from pending to ready (has usage records)"
            )
            return "ready"
        except Exception as e:
            logger.warning(f"Failed to auto-update workspace status to ready: {e}")

    # Check blueprint content
    blueprint = workspace.workspace_blueprint
    if blueprint:
        has_blueprint_content = (
            (blueprint.brief and blueprint.brief.strip())
            or (blueprint.initial_intents and len(blueprint.initial_intents) > 0)
            or (blueprint.tool_connections and len(blueprint.tool_connections) > 0)
        )
        if has_blueprint_content:
            try:
                workspace.launch_status = LaunchStatus.READY
                await store.update_workspace(workspace)
                logger.info(
                    f"Auto-updated workspace {workspace_id} status from pending to ready (has blueprint content)"
                )
                return "ready"
            except Exception as e:
                logger.warning(f"Failed to auto-update workspace status to ready: {e}")

    return "pending"

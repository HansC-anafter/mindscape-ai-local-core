"""Intent steward layout execution."""

import logging
import uuid

from backend.app.models.mindscape import (
    IntentCard,
    IntentLayoutPlan,
    IntentStatus,
    PriorityLevel,
)
from backend.app.services.conversation.intent_steward_core.runtime import utc_now

logger = logging.getLogger(__name__)


async def check_auto_layout_flag(service, profile_id: str, workspace_id: str) -> bool:
    del service, profile_id, workspace_id
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()
        setting = settings_store.get_setting("auto_intent_layout")
        if setting and setting.value:
            if isinstance(setting.value, bool):
                return setting.value
            if isinstance(setting.value, str):
                return setting.value.lower() in ["true", "1", "yes"]
        return False
    except Exception as exc:
        logger.warning(f"Failed to check auto_intent_layout flag: {exc}")
        return False


async def execute_layout_plan(
    service,
    layout_plan: IntentLayoutPlan,
    workspace_id: str,
    profile_id: str,
    turn_id: str,
) -> None:
    try:
        executed_operations = []
        for operation in layout_plan.long_term_intents:
            if operation.operation_type == "CREATE_INTENT_CARD":
                _execute_create_operation(
                    service,
                    layout_plan,
                    operation,
                    executed_operations,
                    workspace_id,
                    profile_id,
                    turn_id,
                )
            elif operation.operation_type == "UPDATE_INTENT_CARD":
                _execute_update_operation(
                    service,
                    operation,
                    executed_operations,
                    workspace_id,
                    turn_id,
                )

        layout_plan.metadata["executed_operations"] = executed_operations
        logger.info(
            f"IntentSteward: Executed {len(executed_operations)} operations "
            f"({sum(1 for op in executed_operations if op['type'] == 'CREATE')} creates, "
            f"{sum(1 for op in executed_operations if op['type'] == 'UPDATE')} updates)"
        )
    except Exception as exc:
        logger.error(f"Failed to execute layout plan: {exc}", exc_info=True)
        layout_plan.metadata["execution_error"] = str(exc)


def _execute_create_operation(
    service,
    layout_plan: IntentLayoutPlan,
    operation,
    executed_operations,
    workspace_id: str,
    profile_id: str,
    turn_id: str,
) -> None:
    try:
        intent_data = operation.intent_data
        new_intent = IntentCard(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            title=intent_data.get("title", ""),
            description=intent_data.get("description", ""),
            status=IntentStatus(intent_data.get("status", "active")),
            priority=PriorityLevel(intent_data.get("priority", "medium")),
            tags=intent_data.get("tags", []),
            category=intent_data.get("category"),
            progress_percentage=intent_data.get("progress_percentage", 0),
            created_at=utc_now(),
            updated_at=utc_now(),
            started_at=None,
            completed_at=None,
            due_date=None,
            parent_intent_id=None,
            child_intent_ids=[],
            metadata={
                "source": "intent_steward_auto",
                "turn_id": turn_id,
                "workspace_id": workspace_id,
                "steward_version": "v2_phase2",
                "relation_signals": operation.relation_signals,
                "confidence": operation.confidence,
                "reasoning": operation.reasoning,
            },
        )
        created_intent = service.store.create_intent(new_intent)
        for mapping in layout_plan.signal_mapping:
            if mapping.signal_id in operation.relation_signals:
                mapping.target_intent_id = created_intent.id
        executed_operations.append(
            {
                "type": "CREATE",
                "intent_id": created_intent.id,
                "title": created_intent.title,
            }
        )
        logger.info(
            f"IntentSteward: Created IntentCard {created_intent.id}: "
            f"{created_intent.title}"
        )
    except Exception as exc:
        logger.error(f"Failed to create IntentCard: {exc}", exc_info=True)


def _execute_update_operation(
    service,
    operation,
    executed_operations,
    workspace_id: str,
    turn_id: str,
) -> None:
    try:
        if not operation.intent_id:
            logger.warning("UPDATE operation missing intent_id, skipping")
            return

        existing_intent = service.store.get_intent(operation.intent_id)
        if not existing_intent:
            logger.warning(f"IntentCard {operation.intent_id} not found, skipping update")
            return

        original_state = {
            "title": existing_intent.title,
            "description": existing_intent.description,
            "priority": existing_intent.priority.value,
            "status": existing_intent.status.value,
            "metadata": existing_intent.metadata.copy()
            if existing_intent.metadata
            else {},
        }

        intent_data = operation.intent_data
        if "title" in intent_data:
            existing_intent.title = intent_data["title"]
        if "description" in intent_data:
            existing_intent.description = intent_data["description"]
        if "priority" in intent_data:
            existing_intent.priority = PriorityLevel(intent_data["priority"])
        if "status" in intent_data:
            existing_intent.status = IntentStatus(intent_data["status"])

        if not existing_intent.metadata:
            existing_intent.metadata = {}
        existing_intent.metadata.update(
            {
                "source": "intent_steward_auto",
                "last_steward_update": turn_id,
                "workspace_id": workspace_id,
                "steward_version": "v2_phase2",
                "relation_signals": operation.relation_signals,
                "confidence": operation.confidence,
                "reasoning": operation.reasoning,
                "rollback_data": original_state,
            }
        )
        existing_intent.updated_at = utc_now()

        updated_intent = service.store.intents.update_intent(existing_intent)
        if updated_intent:
            executed_operations.append(
                {
                    "type": "UPDATE",
                    "intent_id": updated_intent.id,
                    "title": updated_intent.title,
                    "original_state": original_state,
                }
            )
            logger.info(
                f"IntentSteward: Updated IntentCard {updated_intent.id}: "
                f"{updated_intent.title}"
            )
        else:
            logger.warning(f"Failed to update IntentCard {existing_intent.id}")
    except Exception as exc:
        logger.error(f"Failed to update IntentCard: {exc}", exc_info=True)

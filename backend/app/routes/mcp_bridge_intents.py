import logging
import uuid
from typing import Any, Dict

from fastapi import Body, HTTPException

from .mcp_bridge_models import (
    IntentLayoutExecuteRequest,
    IntentSubmitRequest,
    _utc_now,
)

logger = logging.getLogger("backend.app.routes.mcp_bridge")


async def intent_submit(req: IntentSubmitRequest = Body(...)) -> Dict[str, Any]:
    """
    Submit IDE-extracted intents to Workspace.

    - Creates IntentTag entries with source=IDE
    - Skips WS-side IntentExtractor (IDE already did it)
    """
    profile_id = req.profile_id or "default-user"

    try:
        from ..models.mindscape import IntentTag, IntentSource, IntentTagStatus
        from ..services.stores.intent_tags_store import IntentTagsStore
        from ..services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        store.ensure_default_profile()
        intent_tags_store = IntentTagsStore()

        created_tags = []
        for intent in req.extracted_intents:
            tag = IntentTag(
                id=str(uuid.uuid4()),
                workspace_id=req.workspace_id,
                profile_id=profile_id,
                label=intent.label,
                confidence=intent.confidence,
                source=IntentSource.IDE,
                status=IntentTagStatus.CANDIDATE,
                message_id=req.message_id,
                metadata={
                    **(intent.metadata or {}),
                    "submitted_via": "mcp_bridge",
                    "original_message_preview": (
                        req.message[:200] if req.message else None
                    ),
                },
                created_at=_utc_now(),
            )
            try:
                intent_tags_store.create_intent_tag(tag)
                created_tags.append(
                    {
                        "id": tag.id,
                        "label": tag.label,
                        "confidence": tag.confidence,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to create IntentTag '{tag.label}': {e}")

        themes_recorded = 0
        if req.extracted_themes:
            for theme in req.extracted_themes:
                try:
                    theme_tag = IntentTag(
                        id=str(uuid.uuid4()),
                        workspace_id=req.workspace_id,
                        profile_id=profile_id,
                        label=theme,
                        confidence=0.4,
                        source=IntentSource.IDE,
                        status=IntentTagStatus.CANDIDATE,
                        message_id=req.message_id,
                        metadata={"type": "theme", "submitted_via": "mcp_bridge"},
                        created_at=_utc_now(),
                    )
                    intent_tags_store.create_intent_tag(theme_tag)
                    themes_recorded += 1
                except Exception as e:
                    logger.warning(f"Failed to create theme tag '{theme}': {e}")

        return {
            "success": True,
            "intent_tags_created": len(created_tags),
            "themes_recorded": themes_recorded,
            "tags": created_tags,
        }

    except ImportError as e:
        logger.warning(f"Intent submit \u2014 missing dependency: {e}")
        raise HTTPException(status_code=501, detail="IntentTag stores not available")
    except Exception as e:
        logger.error(f"intent_submit failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Intent submission failed: {str(e)}"
        )


async def intent_layout_execute(
    req: IntentLayoutExecuteRequest = Body(...),
) -> Dict[str, Any]:
    """
    Execute an IntentLayoutPlan and create or update IntentCards.

    This is a governed operation that requires confirmation in tool_access_policy.
    Uses IntentStewardService._execute_layout_plan internally.
    """
    profile_id = req.profile_id or "default-user"

    try:
        from ..models.mindscape import (
            IntentLayoutPlan,
            IntentOperation,
            EphemeralTask,
        )
        from ..services.mindscape_store import MindscapeStore
        from ..services.conversation.intent_steward import IntentStewardService

        store = MindscapeStore()
        store.ensure_default_profile()
        steward = IntentStewardService(store=store)

        operations = []
        for action in req.layout_plan.long_term_intents:
            op = IntentOperation(
                operation_type=action.operation_type,
                intent_id=action.intent_id,
                intent_data=action.intent_data,
                relation_signals=action.relation_signals,
                confidence=action.confidence,
                reasoning=action.reasoning,
            )
            operations.append(op)

        ephemeral = []
        if req.layout_plan.ephemeral_tasks:
            for task_data in req.layout_plan.ephemeral_tasks:
                ephemeral.append(
                    EphemeralTask(
                        signal_id=task_data.get("signal_id", str(uuid.uuid4())),
                        title=task_data.get("title", ""),
                        description=task_data.get("description"),
                        reasoning=task_data.get("reasoning", ""),
                    )
                )

        layout_plan = IntentLayoutPlan(
            long_term_intents=operations,
            ephemeral_tasks=ephemeral,
            metadata={
                "source": "mcp_bridge",
                "workspace_id": req.workspace_id,
                "profile_id": profile_id,
                "timestamp": _utc_now().isoformat(),
            },
        )

        turn_id = f"mcp_{uuid.uuid4().hex[:8]}"
        await steward._execute_layout_plan(
            layout_plan=layout_plan,
            workspace_id=req.workspace_id,
            profile_id=profile_id,
            turn_id=turn_id,
        )

        executed_ops = layout_plan.metadata.get("executed_operations", [])

        return {
            "success": True,
            "executed": len(executed_ops),
            "operations": executed_ops,
            "turn_id": turn_id,
        }

    except ImportError as e:
        logger.warning(f"Layout execute \u2014 missing dependency: {e}")
        raise HTTPException(
            status_code=501, detail="IntentSteward service not available"
        )
    except Exception as e:
        logger.error(f"intent_layout_execute failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Layout execution failed: {str(e)}"
        )

import logging
import uuid
from typing import Any, Dict

from fastapi import Body, HTTPException

from .mcp_bridge_models import ChatSyncRequest, _utc_now

logger = logging.getLogger("backend.app.routes.mcp_bridge")


async def chat_sync(req: ChatSyncRequest = Body(...)) -> Dict[str, Any]:
    """
    Sync IDE conversation to Workspace timeline.

    - Records each message as a timeline event
    - Skips WS-side LLM processing when ide_receipts cover the step
    - Returns list of hooks triggered and events emitted
    """
    profile_id = req.profile_id or "default-user"
    thread_id = req.conversation_id  # direct equivalence
    trace_id = req.trace_id or str(uuid.uuid4())

    try:
        from ..services.surface.event_stream import EventStreamService

        event_stream = EventStreamService()

        events_emitted = []
        hooks_triggered = []

        # Record each message as a timeline event
        for msg in req.messages:
            message_id = msg.message_id or trace_id
            event = event_stream.collect_event(
                workspace_id=req.workspace_id,
                source_surface=f"mcp_{req.surface_type}",
                event_type=f"chat_{msg.role}",
                payload={
                    "content": msg.content,
                    "role": msg.role,
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "trace_id": trace_id,
                    "timestamp": msg.timestamp or _utc_now().isoformat(),
                    "playbook_executed": req.playbook_executed,
                },
                actor_id=profile_id,
                correlation_id=trace_id,
            )
            events_emitted.append(
                event.event_id if hasattr(event, "event_id") else str(event)
            )

        try:
            from ..services.mcp_event_hooks import MCPEventHookService

            hook_service = MCPEventHookService(workspace_id=req.workspace_id)

            user_messages = [m for m in req.messages if m.role == "user"]
            last_user_msg = user_messages[-1] if user_messages else None

            if last_user_msg:
                hook_results = await hook_service.on_chat_synced(
                    workspace_id=req.workspace_id,
                    profile_id=profile_id,
                    message=last_user_msg.content,
                    message_id=last_user_msg.message_id or trace_id,
                    trace_id=trace_id,
                    thread_id=thread_id,
                    ide_receipts=(
                        [r.model_dump() for r in req.ide_receipts]
                        if req.ide_receipts
                        else None
                    ),
                )
                hooks_triggered.extend(hook_results.triggered_hooks)
                events_emitted.extend(hook_results.events_emitted)

                if hook_results.skipped_hooks:
                    logger.info(
                        f"chat_sync: Skipped hooks (IDE receipts): "
                        f"{hook_results.skipped_hooks} (trace={trace_id})"
                    )
        except ImportError:
            logger.debug("MCPEventHookService not available, skipping hooks")
        except Exception as hook_err:
            logger.warning(f"Event hook processing failed: {hook_err}")

        receipt_details = []
        try:
            if hook_results:
                for d in hook_results.receipt_decisions:
                    receipt_details.append(
                        {
                            "step": d.step,
                            "action": "skipped" if not d.should_run else "ran",
                            "reason": d.reason,
                        }
                    )
        except NameError:
            pass

        return {
            "synced": True,
            "trace_id": trace_id,
            "thread_id": thread_id,
            "events_emitted": events_emitted,
            "hooks_triggered": hooks_triggered,
            "ide_receipts_applied": [
                d["step"] for d in receipt_details if d["action"] == "skipped"
            ],
            "receipt_details": receipt_details,
            "message_count": len(req.messages),
        }

    except Exception as e:
        logger.error(f"chat_sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat sync failed: {str(e)}")

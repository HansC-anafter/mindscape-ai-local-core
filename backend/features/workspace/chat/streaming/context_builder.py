"""
Context building for streaming responses
"""

import logging
from typing import List, Dict, Any, Optional

from backend.app.services.conversation.context_builder import ContextBuilder
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.playbook_service import PlaybookService
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


async def build_streaming_context(
    workspace_id: str,
    message: str,
    profile_id: str,
    workspace: Workspace,
    store: MindscapeStore,
    timeline_items_store: TimelineItemsStore,
    model_name: Optional[str] = None,
    thread_id: Optional[str] = None,
    hours: int = 24,
) -> Optional[str]:
    """
    Build context for streaming response

    Args:
        workspace_id: Workspace ID
        message: User message
        profile_id: Profile ID
        workspace: Workspace object
        store: MindscapeStore instance
        timeline_items_store: TimelineItemsStore instance
        model_name: Optional model name for context builder
        hours: Hours of history to include

    Returns:
        Context string or None
    """
    # Resolve model_name from workspace preference or system settings if not provided
    if not model_name or str(model_name).strip() == "":
        try:
            from backend.app.services.conversation.chat_model_resolution import (
                resolve_conversational_model_name,
            )

            model_name = resolve_conversational_model_name(
                model_name,
                workspace=workspace,
                db_path=getattr(store, "db_path", None),
            )
            if model_name:
                logger.info(f"Resolved model_name for streaming context: {model_name}")
        except Exception as e:
            logger.warning(
                f"Failed to resolve model_name in build_streaming_context: {e}"
            )

    context_builder = ContextBuilder(
        store=store, timeline_items_store=timeline_items_store, model_name=model_name
    )

    context = await context_builder.build_qa_context(
        workspace_id=workspace_id,
        message=message,
        profile_id=profile_id,
        workspace=workspace,
        thread_id=thread_id,
        hours=hours,
        side_chain_mode="auto",
    )

    if context is not None:
        logger.info(f"Built context length: {len(context)} chars")
        logger.info(
            f"Context contains - Intents: {'Active Intents' in context}, "
            f"Tasks: {'Current Tasks' in context}, "
            f"History: {'Recent Conversation' in context}, "
            f"Timeline: {'Recent Timeline Activity' in context}"
        )
    else:
        logger.warning("Context is None, using empty string")
        context = ""

    return context


def _build_workspace_instruction_for_chat(workspace: Workspace) -> str:
    """Extract workspace instruction for chat pipeline injection.

    Delegates to shared helper for consistent precedence and logging.
    """
    from backend.app.services.workspace_instruction_helper import (
        build_workspace_instruction_block,
    )

    block, _ = build_workspace_instruction_block(workspace, caller="chat")
    return block


async def load_available_playbooks(
    workspace_id: str, locale: str, store: MindscapeStore
) -> List[Dict[str, Any]]:
    """
    Load available playbooks for workspace context

    Args:
        workspace_id: Workspace ID
        locale: Locale for playbook loading
        store: MindscapeStore instance

    Returns:
        List of playbook metadata dicts
    """
    available_playbooks = []
    playbook_codes_seen = set()

    # Evidence Logging
    try:
        from datetime import datetime
        import os

        log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n==== LOAD PLAYBOOKS TRACE {datetime.utcnow()} ====\n")
            f.write(f"Workspace: {workspace_id}\n")
            f.write(f"Locale: {locale}\n")
    except Exception:
        pass

    try:
        # Use PlaybookService for unified query
        playbook_service = PlaybookService(store=store)

        # Load all playbooks (system + capability + user) via unified interface
        all_playbook_metadata = await playbook_service.list_playbooks(
            workspace_id=workspace_id, locale=locale, source=None  # Get all sources
        )

        for metadata in all_playbook_metadata:
            if metadata.playbook_code in playbook_codes_seen:
                continue

            # Extract output_types from metadata
            output_types = getattr(metadata, "output_types", []) or []
            if isinstance(output_types, str):
                output_types = [output_types] if output_types else []

            available_playbooks.append(
                {
                    "playbook_code": metadata.playbook_code,
                    "name": metadata.name,
                    "description": metadata.description or "",
                    "tags": metadata.tags or [],
                    "output_type": output_types[0] if output_types else None,
                    "output_types": output_types,
                }
            )
            playbook_codes_seen.add(metadata.playbook_code)

        logger.info(
            f"Loaded {len(all_playbook_metadata)} playbooks via PlaybookService"
        )
        # Evidence Logging with detailed ig_analyze_following trace
        try:
            log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"Loaded via PlaybookService: {len(all_playbook_metadata)}\n")
                # Trace ig_analyze_following specifically
                for pb in available_playbooks:
                    if "ig_analyze_following" in pb.get("playbook_code", ""):
                        f.write(f"[TRACE] ig_analyze_following found:\n")
                        f.write(f"  playbook_code: {pb.get('playbook_code')}\n")
                        f.write(f"  name: {pb.get('name')}\n")
                        f.write(
                            f"  description: {pb.get('description')[:100] if pb.get('description') else '(EMPTY)'}\n"
                        )
        except Exception:
            pass
    except Exception as e:
        logger.warning(
            f"Failed to load playbooks via PlaybookService: {e}", exc_info=True
        )
        # Evidence Logging
        try:
            log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"PlaybookService Error: {str(e)}\n")
        except Exception:
            pass

    logger.info(
        f"Found {len(available_playbooks)} total playbooks for workspace context"
    )
    return available_playbooks

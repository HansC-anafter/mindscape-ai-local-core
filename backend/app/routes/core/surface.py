"""Surface core API routes."""

import uuid
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List

from ...models.surface import SurfaceDefinition, Command, CommandStatus, SurfaceEvent
from ...services.surface.command_bus import CommandBus, SurfaceRegistry
from ...services.surface.event_stream import EventStreamService

router = APIRouter(prefix="/api/v1", tags=["surface"])

command_bus = CommandBus()
event_stream = EventStreamService()
surface_registry = SurfaceRegistry()


# Auto-register default surfaces on module load
def _register_default_surfaces():
    """Register default surface definitions.

    Note: adapter_class paths are optional and should be provided by cloud layer.
    Local-core only provides the surface definition contract.
    """
    from ...models.surface import SurfaceType, PermissionLevel

    # UI Adapter - Control Surface
    ui_surface = SurfaceDefinition(
        surface_id="mindscape_ui",
        surface_type=SurfaceType.CONTROL,
        display_name="Mindscape UI",
        capabilities=[
            "create_workspace",
            "edit_composition",
            "approve_execution",
            "view_trace",
            "rollback_artifact",
            "manage_preset",
        ],
        permission_level=PermissionLevel.OPERATOR,
        adapter_class=None,  # Provided by cloud layer
        metadata={"type": "web_console"},
    )
    surface_registry.register_surface(ui_surface)

    # LINE Adapter - Delivery Surface
    line_surface = SurfaceDefinition(
        surface_id="line",
        surface_type=SurfaceType.DELIVERY,
        display_name="LINE Official Account",
        capabilities=["receive_message", "send_message", "trigger_preset_command"],
        permission_level=PermissionLevel.CONSUMER,
        adapter_class=None,  # Provided by cloud layer
        metadata={"type": "messaging", "platform": "line"},
    )
    surface_registry.register_surface(line_surface)

    # Instagram Adapter - Delivery Surface
    ig_surface = SurfaceDefinition(
        surface_id="ig",
        surface_type=SurfaceType.DELIVERY,
        display_name="Instagram",
        capabilities=["receive_message", "send_message", "trigger_preset_command"],
        permission_level=PermissionLevel.CONSUMER,
        adapter_class=None,  # Provided by cloud layer
        metadata={"type": "social_media", "platform": "instagram"},
    )
    surface_registry.register_surface(ig_surface)

    # WordPress Adapter - Delivery Surface
    wp_surface = SurfaceDefinition(
        surface_id="wordpress_public",
        surface_type=SurfaceType.DELIVERY,
        display_name="WordPress Public",
        capabilities=["receive_message", "send_message", "trigger_preset_command"],
        permission_level=PermissionLevel.CONSUMER,
        adapter_class=None,  # Provided by cloud layer
        metadata={"type": "cms", "platform": "wordpress"},
    )
    surface_registry.register_surface(wp_surface)


# Register surfaces on module import
_register_default_surfaces()


@router.post("/commands", response_model=Dict[str, Any], status_code=201)
async def dispatch_command(command: Command = Body(...)) -> Dict[str, Any]:
    """
    Dispatch a command from any surface.

    Creates and dispatches a command through the Command Bus.
    """
    try:
        if not command.command_id:
            command.command_id = f"cmd_{uuid.uuid4().hex[:12]}"

        return await command_bus.dispatch_command(command)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to dispatch command: {str(e)}"
        )


@router.post("/commands/{command_id}/approve", response_model=Dict[str, Any])
async def approve_command(command_id: str) -> Dict[str, Any]:
    """
    Approve a pending command.

    Approves a command that requires approval and executes it.
    """
    try:
        return await command_bus.approve_command(command_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to approve command: {str(e)}"
        )


@router.post("/commands/{command_id}/reject", response_model=Dict[str, Any])
async def reject_command(
    command_id: str, reason: Optional[str] = Body(None, embed=True)
) -> Dict[str, Any]:
    """
    Reject a pending command.

    Rejects a command that requires approval.
    """
    try:
        return await command_bus.reject_command(command_id, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reject command: {str(e)}"
        )


@router.get("/commands/{command_id}", response_model=Command)
async def get_command(command_id: str) -> Command:
    """
    Get command by ID.

    Returns a specific command.
    """
    command = command_bus.get_command(command_id)
    if not command:
        raise HTTPException(status_code=404, detail=f"Command {command_id} not found")
    return command


@router.get("/commands", response_model=List[Command])
async def list_commands(
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID"),
    status: Optional[CommandStatus] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
) -> List[Command]:
    """
    List commands with filters.

    Returns a list of commands, optionally filtered by workspace and status.
    """
    return command_bus.list_commands(
        workspace_id=workspace_id, status=status, limit=limit
    )


@router.post("/events", response_model=SurfaceEvent, status_code=201)
async def collect_event(
    workspace_id: str = Body(...),
    source_surface: str = Body(...),
    event_type: str = Body(...),
    payload: Dict[str, Any] = Body(default_factory=dict),
    actor_id: Optional[str] = Body(None),
    command_id: Optional[str] = Body(None),
    thread_id: Optional[str] = Body(None),
    correlation_id: Optional[str] = Body(None),
    parent_event_id: Optional[str] = Body(None),
    execution_id: Optional[str] = Body(None),
) -> SurfaceEvent:
    """
    Collect an event from any surface.

    Creates and stores a surface event.
    """
    try:
        return event_stream.collect_event(
            workspace_id=workspace_id,
            source_surface=source_surface,
            event_type=event_type,
            payload=payload,
            actor_id=actor_id,
            command_id=command_id,
            thread_id=thread_id,
            correlation_id=correlation_id,
            parent_event_id=parent_event_id,
            execution_id=execution_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to collect event: {str(e)}"
        )


@router.get("/events", response_model=List[SurfaceEvent])
async def get_events(
    workspace_id: str = Query(..., description="Workspace ID"),
    surface_filter: Optional[str] = Query(None, description="Filter by source surface"),
    event_type_filter: Optional[str] = Query(None, description="Filter by event type"),
    actor_filter: Optional[str] = Query(None, description="Filter by actor ID"),
    command_id_filter: Optional[str] = Query(None, description="Filter by command ID"),
    thread_id_filter: Optional[str] = Query(None, description="Filter by thread ID"),
    correlation_id_filter: Optional[str] = Query(
        None, description="Filter by correlation ID"
    ),
    pack_id_filter: Optional[str] = Query(None, description="Filter by pack ID (BYOP)"),
    card_id_filter: Optional[str] = Query(None, description="Filter by card ID (BYOP)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
) -> List[SurfaceEvent]:
    """
    Get events with filters.

    Returns a list of events, optionally filtered by various criteria.
    Supports BYOP/BYOL filtering via pack_id and card_id.
    """
    return event_stream.get_events(
        workspace_id=workspace_id,
        surface_filter=surface_filter,
        event_type_filter=event_type_filter,
        actor_filter=actor_filter,
        command_id_filter=command_id_filter,
        thread_id_filter=thread_id_filter,
        correlation_id_filter=correlation_id_filter,
        pack_id_filter=pack_id_filter,
        card_id_filter=card_id_filter,
        limit=limit,
    )


@router.post("/surfaces", response_model=SurfaceDefinition, status_code=201)
async def register_surface(surface: SurfaceDefinition = Body(...)) -> SurfaceDefinition:
    """
    Register a surface.

    Registers a new surface definition in the Surface Registry.
    """
    try:
        return surface_registry.register_surface(surface)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to register surface: {str(e)}"
        )


@router.get("/surfaces/{surface_id}", response_model=SurfaceDefinition)
async def get_surface(surface_id: str) -> SurfaceDefinition:
    """
    Get surface by ID.

    Returns a specific surface definition.
    """
    surface = surface_registry.get_surface(surface_id)
    if not surface:
        raise HTTPException(status_code=404, detail=f"Surface {surface_id} not found")
    return surface


@router.get("/surfaces", response_model=List[SurfaceDefinition])
async def list_surfaces() -> List[SurfaceDefinition]:
    """
    List all registered surfaces.

    Returns a list of all registered surface definitions.
    """
    return surface_registry.list_surfaces()


# ============================================
# External Context API (P3: Context Passthrough)
# ============================================


@router.post("/surfaces/external-context", status_code=201)
async def record_external_context(
    workspace_id: str = Body(...),
    surface_type: str = Body(...),
    surface_user_id: str = Body(...),
    tool_called: str = Body(...),
    original_message: Optional[str] = Body(None),
    conversation_id: Optional[str] = Body(None),
    intent_hint: Optional[str] = Body(None),
    timestamp: Optional[str] = Body(None),
) -> Dict[str, Any]:
    """
    Record external context from MCP Gateway.

    When external AI tools call Mindscape tools via MCP Gateway,
    this endpoint records the context for Intent/Seed tracking.

    Returns intent_id and seed_id if extraction was successful.
    """
    import uuid
    from datetime import datetime as dt

    try:
        # Create event for timeline tracking
        event = event_stream.collect_event(
            workspace_id=workspace_id,
            source_surface=f"mcp_{surface_type}",
            event_type="external_tool_call",
            payload={
                "original_message": original_message,
                "tool_called": tool_called,
                "surface_user_id": surface_user_id,
                "conversation_id": conversation_id,
                "intent_hint": intent_hint,
            },
            actor_id=surface_user_id,
        )

        intent_id = None
        seed_id = None

        # Attempt intent extraction if we have a message
        if original_message:
            try:
                from ...services.conversation.intent_extractor import IntentExtractor
                from ...services.stores.mindscape_store import MindscapeStore
                from ...services.stores.timeline_items_store import TimelineItemsStore
                from ...adapters.local.local_intent_registry_adapter import (
                    LocalIntentRegistryAdapter,
                )

                # Initialize stores (lightweight - uses connection pool)
                store = MindscapeStore()
                timeline_store = TimelineItemsStore()
                intent_registry = LocalIntentRegistryAdapter()

                extractor = IntentExtractor(
                    store=store,
                    timeline_items_store=timeline_store,
                    intent_registry=intent_registry,
                )

                # Extract intent from external message
                intent_tags = extractor.extract_intents(
                    workspace_id=workspace_id,
                    profile_id=surface_user_id,
                    message=original_message,
                    message_id=event.event_id,
                )

                if intent_tags:
                    intent_id = (
                        intent_tags[0].id
                        if hasattr(intent_tags[0], "id")
                        else str(uuid.uuid4())
                    )
                    # Create seed from intent if significant
                    if len(intent_tags) > 0:
                        seed_id = f"seed_{event.event_id[:8]}"

            except ImportError as ie:
                # Intent extraction not available in this environment
                pass
            except Exception as extract_error:
                # Log but don't fail the request
                import logging

                logging.getLogger(__name__).warning(
                    f"Intent extraction failed: {extract_error}"
                )

        return {
            "success": True,
            "event_id": event.event_id,
            "intent_id": intent_id,
            "seed_id": seed_id,
            "message": "External context recorded successfully",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to record external context: {str(e)}"
        )

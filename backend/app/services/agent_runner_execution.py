"""Agent execution flows for the agent runner facade."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from backend.app.models.mindscape import (
    AgentExecution,
    AgentResponse,
    EventActor,
    EventType,
    MindEvent,
    RunAgentRequest,
)

logger = logging.getLogger(__name__)


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def run_agent(runner, profile_id: str, request: RunAgentRequest) -> AgentResponse:
    """Execute an agent with the given request."""

    execution_id = str(uuid.uuid4())
    start_time = utc_now()

    execution = AgentExecution(
        id=execution_id,
        profile_id=profile_id,
        agent_type=request.agent_type,
        task=request.task,
        intent_ids=request.intent_ids,
        status="running",
        started_at=start_time,
    )

    try:
        profile = None
        active_intents = []

        if request.use_mindscape:
            profile = runner.store.get_profile(profile_id)
            if profile:
                active_intents = runner.store.list_intents(profile_id)

        execution.used_profile = profile.model_dump() if profile else None
        execution.used_intents = [intent.model_dump() for intent in active_intents]

        backend = runner.backend_manager.get_active_backend(profile_id)
        agent_response = await backend.run_agent(
            task=request.task,
            agent_type=request.agent_type,
            profile=profile,
            active_intents=active_intents,
            metadata={"intent_ids": request.intent_ids},
        )

        response_text = agent_response.output

        end_time = utc_now()
        execution.status = "completed"
        execution.completed_at = end_time
        execution.duration_seconds = (end_time - start_time).total_seconds()
        execution.output = response_text
        execution.metadata = agent_response.metadata

        runner.store.create_agent_execution(execution)

        try:
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=end_time,
                actor=EventActor.ASSISTANT,
                channel="api",
                profile_id=profile_id,
                project_id=None,
                event_type=EventType.AGENT_EXECUTION,
                payload={
                    "execution_id": execution_id,
                    "agent_type": request.agent_type,
                    "task": request.task[:200],
                    "status": "completed",
                    "duration_seconds": execution.duration_seconds,
                    "intent_ids": request.intent_ids,
                },
                entity_ids=request.intent_ids,
                metadata={
                    "output_length": len(response_text) if response_text else 0,
                    "use_mindscape": request.use_mindscape,
                },
            )
            runner.store.create_event(event)
        except Exception as exc:
            logger.warning("Failed to record agent execution event: %s", exc)

        try:
            await runner._extract_seeds_from_execution(
                profile_id=profile_id,
                execution_id=execution_id,
                task=request.task,
                output=response_text,
            )
        except Exception as exc:
            logger.warning("Failed to extract seeds: %s", exc)

        try:
            await runner._observe_habits_from_execution(
                profile_id=profile_id, execution=execution, profile=profile
            )
        except Exception as exc:
            logger.warning("Failed to observe habits from execution: %s", exc)

        return AgentResponse(
            execution_id=execution_id,
            status="completed",
            output=response_text,
            used_profile=execution.used_profile,
            used_intents=execution.used_intents,
            metadata=agent_response.metadata,
        )

    except Exception as exc:
        logger.error("Agent execution failed: %s", exc)

        end_time = utc_now()
        execution.status = "failed"
        execution.completed_at = end_time
        execution.duration_seconds = (end_time - start_time).total_seconds()
        execution.error_message = str(exc)

        runner.store.create_agent_execution(execution)

        try:
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=end_time,
                actor=EventActor.SYSTEM,
                channel="api",
                profile_id=profile_id,
                project_id=None,
                event_type=EventType.AGENT_EXECUTION,
                payload={
                    "execution_id": execution_id,
                    "agent_type": request.agent_type,
                    "task": request.task[:200],
                    "status": "failed",
                    "error_message": str(exc)[:500],
                    "duration_seconds": execution.duration_seconds,
                    "intent_ids": request.intent_ids,
                },
                entity_ids=request.intent_ids,
                metadata={"use_mindscape": request.use_mindscape},
            )
            runner.store.create_event(event)
        except Exception as event_exc:
            logger.warning("Failed to record failed agent execution event: %s", event_exc)

        try:
            await runner._extract_seeds_from_execution(
                profile_id=profile_id,
                execution_id=execution_id,
                task=request.task,
                output=None,
            )
        except Exception as seed_exc:
            logger.warning("Failed to extract seeds from failed execution: %s", seed_exc)

        try:
            await runner._observe_habits_from_execution(
                profile_id=profile_id, execution=execution, profile=profile
            )
        except Exception as habit_exc:
            logger.warning(
                "Failed to observe habits from failed execution: %s", habit_exc
            )

        return AgentResponse(
            execution_id=execution_id,
            status="failed",
            error_message=str(exc),
            metadata={"agent_type": request.agent_type},
        )


async def run_agents_parallel(
    runner,
    profile_id: str,
    task: str,
    agent_types: List[str],
    use_mindscape: bool = True,
    intent_ids: List[str] = None,
) -> List[AgentResponse]:
    """Run multiple agents in parallel for the same task."""
    if not task:
        raise ValueError("Task description required")

    profile = None
    active_intents = []

    if use_mindscape:
        profile = runner.store.get_profile(profile_id)
        if profile:
            active_intents = runner.store.list_intents(profile_id)

    backend = runner.backend_manager.get_active_backend(profile_id)

    tasks = []
    for agent_type in agent_types:
        if agent_type not in ["planner", "writer", "coach", "coder"]:
            continue

        async def run_single_agent(at: str) -> AgentResponse:
            execution_id = str(uuid.uuid4())
            try:
                agent_response = await backend.run_agent(
                    task=task,
                    agent_type=at,
                    profile=profile,
                    active_intents=active_intents,
                    metadata={
                        "intent_ids": intent_ids or [],
                        "parallel_execution": True,
                    },
                )
                return AgentResponse(
                    execution_id=execution_id,
                    status=agent_response.status,
                    output=agent_response.output,
                    error_message=agent_response.error_message,
                    used_profile=profile.model_dump() if profile else None,
                    used_intents=[intent.model_dump() for intent in active_intents],
                    metadata={**agent_response.metadata, "agent_type": at},
                )
            except Exception as exc:
                logger.error("Parallel agent execution failed for %s: %s", at, exc)
                return AgentResponse(
                    execution_id=execution_id,
                    status="failed",
                    error_message=str(exc),
                    metadata={"agent_type": at},
                )

        tasks.append(run_single_agent(agent_type))

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    result = []
    for response in responses:
        if isinstance(response, Exception):
            logger.error("Agent execution exception: %s", response)
            result.append(
                AgentResponse(
                    execution_id=str(uuid.uuid4()),
                    status="failed",
                    error_message=str(response),
                    metadata={},
                )
            )
        else:
            result.append(response)

    return result

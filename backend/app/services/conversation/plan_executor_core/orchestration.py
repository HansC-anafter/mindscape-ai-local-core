import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from backend.app.models.workspace_runtime_profile import StopConditions

logger = logging.getLogger(__name__)


@dataclass
class ExecutionOrchestrationState:
    orchestrator: Optional[Any] = None
    eligible_agent_ids: Tuple[str, ...] = ()
    ready_wave_index: int = 0
    primary_execution_id: Optional[str] = None
    registered_execution_ids: List[str] = field(default_factory=list)

    def remember_primary_execution_id(self, execution_id: Optional[str]) -> None:
        if execution_id and self.primary_execution_id is None:
            self.primary_execution_id = execution_id

    @property
    def current_agent_id(self) -> Optional[str]:
        """Compatibility projection; parallel waves intentionally have no singleton."""
        if len(self.eligible_agent_ids) == 1:
            return next(iter(self.eligible_agent_ids))
        return None

    def build_agent_execution_units(self, task_id: Optional[str]) -> List[Dict[str, Any]]:
        """Build compact DAG-unit handoff records for the existing execution owner."""
        node_id = task_id or "unassigned"
        return [
            {
                "unit_id": f"{node_id}:wave-{self.ready_wave_index}:{agent_id}",
                "agent_id": agent_id,
                "ready_wave": self.ready_wave_index,
            }
            for agent_id in self.eligible_agent_ids
        ]


async def _collect_agent_roster(
    task_plans: List[Any],
    ctx: Any,
    resolve_playbook: Callable[..., Awaitable[Any]],
) -> Dict[str, Any]:
    agent_roster: Dict[str, Any] = {}

    for task_plan in task_plans:
        try:
            resolved_playbook = await resolve_playbook(
                pack_id=task_plan.pack_id,
                ctx=ctx,
            )
            if (
                resolved_playbook
                and resolved_playbook.playbook
                and resolved_playbook.playbook.agent_roster
            ):
                # Later playbooks override earlier ones on agent_id conflicts.
                agent_roster.update(resolved_playbook.playbook.agent_roster)
        except Exception as exc:
            logger.debug(
                "Failed to load agent_roster from playbook %s: %s",
                task_plan.pack_id,
                exc,
            )

    return agent_roster


async def initialize_execution_orchestration(
    *,
    execution_plan: Any,
    ctx: Any,
    workspace: Any,
    runtime_profile: Any,
    stop_conditions: Optional[StopConditions],
    message_id: str,
    resolve_playbook: Callable[..., Awaitable[Any]],
    event_store_factory: Optional[Callable[[], Any]] = None,
) -> ExecutionOrchestrationState:
    state = ExecutionOrchestrationState()
    if not runtime_profile or not runtime_profile.topology_routing:
        return state

    try:
        from backend.app.services.orchestration.multi_agent_orchestrator import (
            MultiAgentOrchestrator,
        )
        from backend.app.services.orchestration.orchestrator_registry import (
            get_orchestrator_registry,
        )
        from backend.app.services.orchestration.topology_validator import (
            TopologyValidationError,
            TopologyValidator,
        )

        agent_roster = await _collect_agent_roster(
            execution_plan.tasks,
            ctx,
            resolve_playbook,
        )
        if not agent_roster:
            raise ValueError(
                "Topology routing is configured but no agent_roster found in playbooks. "
                "Please ensure playbooks define agent_roster when using topology_routing."
            )

        validator = TopologyValidator()
        try:
            validator.validate(runtime_profile.topology_routing, agent_roster)
            logger.info(
                "Topology validated successfully: %s agents in roster",
                len(agent_roster),
            )
        except TopologyValidationError as exc:
            logger.error("Topology validation failed: %s", exc)
            raise ValueError(f"Invalid topology configuration: {exc}") from exc

        if event_store_factory is None:
            from backend.app.services.stores.postgres.events_store import (
                PostgresEventsStore,
            )

            event_store_factory = PostgresEventsStore

        state.orchestrator = MultiAgentOrchestrator(
            agent_roster=agent_roster,
            topology=runtime_profile.topology_routing,
            loop_budget=getattr(runtime_profile, "loop_budget", None),
            stop_conditions=stop_conditions,
            workspace_id=workspace.id if workspace else None,
            profile_id=getattr(runtime_profile, "profile_id", None),
            event_store=event_store_factory(),
        )
        logger.info(
            "MultiAgentOrchestrator initialized with %s agents",
            len(agent_roster),
        )

        get_orchestrator_registry().register(message_id, state.orchestrator)
        state.registered_execution_ids.append(message_id)

        initial_agents = state.orchestrator.get_next_agents(current_agent_id=None)
        if initial_agents:
            state.orchestrator.set_current_agents(initial_agents)
            logger.info(
                "MultiAgentOrchestrator: Initial eligible agents=%s",
                initial_agents,
            )
        else:
            logger.warning("MultiAgentOrchestrator: No initial agents found")
    except Exception as exc:
        logger.warning(
            "Failed to initialize MultiAgentOrchestrator: %s",
            exc,
            exc_info=True,
        )

    return state


def advance_execution_orchestration(
    state: ExecutionOrchestrationState,
    task_index: int,
) -> bool:
    orchestrator = state.orchestrator
    if not orchestrator:
        return True

    if not state.eligible_agent_ids:
        next_agents = orchestrator.get_next_agents(current_agent_id=None)
    else:
        next_agents = []
        for current_agent_id in state.eligible_agent_ids:
            next_agents.extend(
                orchestrator.get_next_agents(current_agent_id=current_agent_id)
            )
        next_agents = list(dict.fromkeys(next_agents))
        if not next_agents:
            next_agents = list(state.eligible_agent_ids)

    next_wave = tuple(next_agents)
    if next_wave and next_wave != state.eligible_agent_ids:
        state.eligible_agent_ids = next_wave
        state.ready_wave_index += 1
        orchestrator.set_current_agents(list(next_wave))
        logger.info(
            "MultiAgentOrchestrator: Eligible ready wave=%s",
            list(next_wave),
        )
        orchestrator.record_turn()

    if orchestrator.topology.default_pattern == "loop":
        if task_index == 1 or (
            task_index > 1
            and state.eligible_agent_ids
            and set(state.eligible_agent_ids)
            == set(orchestrator.get_next_agents(current_agent_id=None))
            if orchestrator.state.visited_agents
            else False
        ):
            orchestrator.record_iteration()

    if not orchestrator.should_stop():
        return True

    logger.warning(
        "MultiAgentOrchestrator: Stop conditions met. "
        "State: iteration=%s, turn=%s, step=%s, tool_call=%s, error=%s",
        orchestrator.state.iteration_count,
        orchestrator.state.turn_count,
        orchestrator.state.step_count,
        orchestrator.state.tool_call_count,
        orchestrator.state.error_count,
    )
    return False


def register_execution_with_orchestrator(
    state: Optional[ExecutionOrchestrationState],
    execution_id: Optional[str],
    message_id: str,
) -> None:
    if not state or not state.orchestrator or not execution_id:
        return

    from backend.app.services.orchestration.orchestrator_registry import (
        get_orchestrator_registry,
    )

    state.remember_primary_execution_id(execution_id)
    state.orchestrator.execution_id = execution_id

    orchestrator_registry = get_orchestrator_registry()
    for key, label in (
        (execution_id, "execution_id"),
        (message_id, "message_id"),
        (message_id, "trace_id"),
    ):
        if not key or key in state.registered_execution_ids:
            if key and label == "execution_id":
                logger.debug(
                    "OrchestratorRegistry: %s=%s already registered, skipping duplicate",
                    label,
                    key,
                )
            continue

        orchestrator_registry.register(key, state.orchestrator)
        state.registered_execution_ids.append(key)
        if label == "execution_id":
            logger.info(
                "OrchestratorRegistry: Registered orchestrator for execution_id=%s "
                "(tool_executor will use this key for tool_call counting)",
                key,
            )
        else:
            logger.debug(
                "OrchestratorRegistry: Also registered with %s=%s as fallback",
                label,
                key,
            )


def cleanup_execution_orchestration(
    state: ExecutionOrchestrationState,
) -> None:
    if not state.orchestrator:
        return

    try:
        from backend.app.services.orchestration.orchestrator_registry import (
            get_orchestrator_registry,
        )

        get_orchestrator_registry().unregister_by_orchestrator(state.orchestrator)
        logger.debug(
            "OrchestratorRegistry: Cleaned up orchestrator registrations "
            "(was registered with %s keys: %s)",
            len(state.registered_execution_ids),
            state.registered_execution_ids,
        )
    except Exception as exc:
        logger.warning(
            "Failed to cleanup orchestrator registrations: %s",
            exc,
            exc_info=True,
        )

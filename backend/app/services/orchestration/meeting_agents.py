"""
Default multi-agent roster and topology for governance meetings.
"""

from typing import Any, Dict, Optional

from backend.app.models.playbook import AgentDefinition
from backend.app.models.workspace_runtime_profile import TopologyRouting


MEETING_AGENT_ROSTER: Dict[str, AgentDefinition] = {
    "facilitator": AgentDefinition(
        agent_id="facilitator",
        agent_name="Facilitator",
        role="facilitator",
        system_prompt=(
            "You facilitate the meeting, manage rounds, and decide when to converge."
        ),
        tools=["meeting_round_control"],
        responsibility_boundary="orchestration_only",
    ),
    "planner": AgentDefinition(
        agent_id="planner",
        agent_name="Planner",
        role="planner",
        system_prompt=(
            "You propose practical plans, steps, and evidence for execution."
        ),
        tools=["workspace_query", "knowledge_search"],
        responsibility_boundary="proposal_and_planning",
    ),
    "critic": AgentDefinition(
        agent_id="critic",
        agent_name="Critic",
        role="critic",
        system_prompt=(
            "You identify risks, missing assumptions, and safer alternatives."
        ),
        tools=["workspace_query", "knowledge_search"],
        responsibility_boundary="risk_and_validation",
    ),
    "executor": AgentDefinition(
        agent_id="executor",
        agent_name="Executor",
        role="executor",
        system_prompt=(
            "You convert finalized decisions into action items and executable tasks."
        ),
        tools=["playbook_resolve", "task_create"],
        responsibility_boundary="execution_only",
    ),
}


MEETING_TOPOLOGY = TopologyRouting(
    default_pattern="hierarchical",
    agent_routing_rules={
        "facilitator": ["planner"],
        "planner": ["critic"],
        "critic": ["facilitator"],
        "executor": [],
    },
    pattern_config={
        "root_agent": "facilitator",
        "terminal_agent": "executor",
    },
)


def build_meeting_roster(
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, AgentDefinition]:
    """Build meeting agent roster for a given context.

    Customizes agent prompts and tools based on workspace/project metadata.
    Falls back to the default roster if no customization is found.

    Args:
        workspace_id: Optional workspace scope.
        project_id: Optional project scope.
        workspace_metadata: Pre-loaded workspace metadata (avoids async IO).

    Returns:
        Agent roster dictionary keyed by agent_id.
    """
    roster = dict(MEETING_AGENT_ROSTER)
    if workspace_metadata:
        agent_config = workspace_metadata.get("meeting_agents")
        if agent_config and isinstance(agent_config, dict):
            roster = _apply_agent_overrides(roster, agent_config)
    return roster


def _apply_agent_overrides(
    roster: Dict[str, AgentDefinition],
    config: Dict[str, Any],
) -> Dict[str, AgentDefinition]:
    """Apply workspace-level overrides to agent definitions."""
    for agent_id, overrides in config.items():
        if agent_id not in roster or not isinstance(overrides, dict):
            continue
        agent = roster[agent_id]
        suffix = overrides.get("system_prompt_suffix")
        new_prompt = agent.system_prompt
        if suffix and isinstance(suffix, str):
            new_prompt = agent.system_prompt + "\n" + suffix
        new_tools = overrides.get("tools", agent.tools)
        if new_prompt != agent.system_prompt or new_tools != agent.tools:
            roster[agent_id] = AgentDefinition(
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                role=agent.role,
                system_prompt=new_prompt,
                tools=new_tools,
                responsibility_boundary=agent.responsibility_boundary,
            )
    return roster

"""
Default multi-agent roster and topology for governance meetings.
"""

from typing import Any, Dict, Optional

from backend.app.models.playbook import AgentDefinition
from backend.app.models.workspace_runtime_profile import TopologyRouting


MEETING_ROLE_ROSTER: Dict[str, AgentDefinition] = {
    "facilitator": AgentDefinition(
        agent_id="facilitator",
        agent_name="Facilitator",
        role="facilitator",
        system_prompt=(
            "You facilitate the meeting, manage rounds, and decide when to converge."
        ),
        tools=["meeting_round_control"],
        responsibility_boundary="orchestration_only",
        critical_rules=[
            "NEVER declare convergence before the critic has responded in the current round.",
            "NEVER skip planner proposals — every round must include a planner turn.",
            "NEVER take sides — summarize perspectives neutrally.",
            "If the round count reaches max_rounds, you MUST converge.",
        ],
        communication_style=(
            "Neutral moderator. Summarize each role's input concisely. "
            "Use structured format: Progress → Open Issues → Next Step."
        ),
        success_metrics=[
            "All agenda items addressed before convergence.",
            "Convergence achieved within round budget.",
        ],
        capability_profile="fast",
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
        critical_rules=[
            "NEVER propose a plan without at least one verification or rollback step.",
            "NEVER ignore critic feedback — address each concern explicitly.",
            "NEVER assign tasks outside the available tool/playbook inventory.",
            "Every step must have a clear owner and measurable outcome.",
        ],
        communication_style=(
            "Structured planner. Use numbered steps with ownership and deliverables. "
            "Format: Step N → Owner → Deliverable → Verification."
        ),
        success_metrics=[
            "Plan has concrete, executable steps with clear ownership.",
            "Every critic concern is either addressed or explicitly acknowledged.",
        ],
        capability_profile="precise",
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
        critical_rules=[
            "NEVER approve a plan without raising at least one concern or risk.",
            "NEVER propose alternative plans — stay in critique mode.",
            "If no risk is found, state explicitly why the plan is safe.",
            "NEVER repeat the planner's proposal — focus only on gaps and risks.",
        ],
        communication_style=(
            "Constructive skepticism. Frame concerns as questions, not rejections. "
            "Format: Risk → Impact → Suggested Mitigation."
        ),
        success_metrics=[
            "At least one non-trivial risk identified per plan.",
            "Each risk includes impact assessment and mitigation suggestion.",
        ],
        capability_profile="precise",
    ),
    "executor": AgentDefinition(
        agent_id="executor",
        agent_name="Program Synthesizer",
        role="executor",
        system_prompt=(
            "You synthesize finalized decisions into a structured program specification. "
            "Output workstreams, milestones, dependency graph, and target outputs. "
            "Do NOT output low-level action item JSON — output program structure."
        ),
        tools=["playbook_resolve", "task_create"],
        responsibility_boundary="execution_only",
        critical_rules=[
            "NEVER modify the user's original request or add agenda items not discussed.",
            "NEVER choose a playbook_code not listed in Available Playbooks.",
            "Produce as many action items as the task requires. "
            "For multi-deliverable requests, ensure every deliverable has corresponding action items.",
            "All action items target the current workspace. Do NOT set target_workspace_id.",
        ],
        communication_style=(
            "Precise executor. Output valid JSON only. No commentary outside JSON array."
        ),
        success_metrics=[
            "All action items map to available playbooks or tools.",
            "JSON output passes schema validation.",
        ],
        capability_profile="safe_write",
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
    roster = dict(MEETING_ROLE_ROSTER)
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
                critical_rules=agent.critical_rules,
                communication_style=agent.communication_style,
                success_metrics=agent.success_metrics,
            )
    return roster


# ────────────────────────────────────────────────────────────────────
# OP-4: Deliberation Depth — internal effort control, NOT routing.
# ────────────────────────────────────────────────────────────────────

from enum import Enum


class DeliberationDepth(str, Enum):
    """Internal deliberation effort control for MeetingEngine (OP-4).

    NOT a routing decision — IngressRouter remains the sole routing
    authority.  This only controls how many rounds and which agents
    participate within an already-routed meeting.
    """

    SHALLOW = "shallow"  # 1 round, minimal roster (no critic)
    STANDARD = "standard"  # default, 2-3 rounds, full roster
    DEEP = "deep"  # more rounds, critic reinforced


# Depth → max_rounds override
DEPTH_ROUND_CAPS: Dict[str, int] = {
    "shallow": 1,
    "standard": 3,
    "deep": 5,
}

# Depth → agent roster filter
DEPTH_ROSTER_KEYS: Dict[str, list] = {
    "shallow": ["facilitator", "planner", "executor"],
    "standard": ["facilitator", "planner", "critic", "executor"],
    "deep": ["facilitator", "planner", "critic", "executor"],
}


def get_round_roster(
    depth: DeliberationDepth,
    full_roster: Optional[Dict[str, AgentDefinition]] = None,
) -> Dict[str, AgentDefinition]:
    """Return depth-aware agent roster for a given round.

    SHALLOW skips the critic to reduce latency on trivial requests.
    STANDARD and DEEP use the full roster.
    """
    roster = full_roster or dict(MEETING_ROLE_ROSTER)
    keys = DEPTH_ROSTER_KEYS.get(depth.value, list(roster.keys()))
    return {k: v for k, v in roster.items() if k in keys}


def select_deliberation_depth(
    agenda_items: int = 1,
    estimated_action_count: int = 1,
    has_tool_ambiguity: bool = False,
    budget_headroom_pct: float = 1.0,
) -> DeliberationDepth:
    """Select deliberation depth from meeting-internal factors.

    Conservative first release:
    - Only obvious single-playbook requests go SHALLOW
    - Default everything else to STANDARD
    - DEEP requires explicit multi-step or high-risk signals

    Does NOT use routing information — that would violate C1
    (IngressRouter as sole routing authority).
    """
    # SHALLOW: single agenda item, single action, no ambiguity, plenty of budget
    if (
        agenda_items <= 1
        and estimated_action_count <= 1
        and not has_tool_ambiguity
        and budget_headroom_pct > 0.7
    ):
        return DeliberationDepth.SHALLOW

    # DEEP: many agenda items or actions, or tight budget needs careful planning
    if agenda_items >= 4 or estimated_action_count >= 4 or budget_headroom_pct < 0.3:
        return DeliberationDepth.DEEP

    return DeliberationDepth.STANDARD

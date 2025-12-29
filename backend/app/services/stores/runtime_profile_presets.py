"""
Runtime Profile Preset Templates

Defines preset templates for common use cases:
- Security: Strict confirmation policies, complete quality gates, conservative tool policies
- Agile: Minimal confirmation, fast execution, lenient tool policies
- Research: Detailed output, citation requirements, complete decision logs
"""

from backend.app.models.workspace_runtime_profile import (
    WorkspaceRuntimeProfile,
    InteractionBudget,
    OutputContract,
    ConfirmationPolicy,
    ToolPolicy,
    LoopBudget,
    StopConditions,
    QualityGates,
    TopologyRouting,
    RationaleLevel,
    CodingStyle,
    WritingStyle
)


def create_security_preset(workspace_id: str) -> WorkspaceRuntimeProfile:
    """
    Create Security preset template

    Characteristics:
    - Strict confirmation policies (all writes require approval)
    - Complete quality gates (lint, tests, docs)
    - Conservative tool policies (denylist for high-risk tools)
    - Detailed output contract
    """
    return WorkspaceRuntimeProfile(
        workspace_id=workspace_id,
        default_mode="qa",  # Prefer discussion over execution

        # Interaction Budget: Conservative limits
        interaction_budget=InteractionBudget(
            max_questions_per_turn=1,  # Limit questions
            assume_defaults=False,  # Don't assume defaults
            require_assumptions_list=True  # Require assumptions list
        ),

        # Output Contract: Detailed and structured
        output_contract=OutputContract(
            coding_style=CodingStyle.EXPLAIN_FIRST,  # Explain before code
            writing_style=WritingStyle.STRUCTURE_FIRST,  # Structure first
            minimize_explanation=False,  # Detailed explanations
            show_rationale_level=RationaleLevel.DETAILED,  # Full decision log
            include_decision_log=True  # Include decision log
        ),

        # Confirmation Policy: Strict (all writes require approval)
        confirmation_policy=ConfirmationPolicy(
            confirm_external_write=True,
            confirm_soft_write=True,
            auto_read=True,
            require_explicit_confirm=True
        ),

        # Tool Policy: Conservative (denylist for high-risk tools)
        tool_policy=ToolPolicy(
            allowlist=None,  # Allow all by default
            denylist=["destructive", "high_risk"],  # Deny high-risk tools
            require_approval_for_capabilities=["external_write", "soft_write"],
            max_tool_call_chain=5  # Limit tool call chains
        ),

        # Loop Budget: Conservative limits
        loop_budget=LoopBudget(
            max_iterations=5,
            max_turns=10,
            max_steps=20,
            max_tool_calls=15
        ),

        # Stop Conditions: Strict definition of done
        stop_conditions=StopConditions(
            definition_of_done=["lint passed", "tests passed", "docs updated"],
            max_errors=2,
            max_retries=1
        ),

        # Quality Gates: Complete checks
        quality_gates=QualityGates(
            require_lint=True,
            require_tests=True,
            require_docs=True,
            require_changelist=True,
            require_rollback_plan=True,
            require_citations=False
        ),

        # Topology: Sequential (safe, predictable)
        topology_routing=TopologyRouting(
            default_pattern="sequential",
            agent_routing_rules={}
        )
    )


def create_agile_preset(workspace_id: str) -> WorkspaceRuntimeProfile:
    """
    Create Agile preset template

    Characteristics:
    - Minimal confirmation (only external writes)
    - Fast execution (higher limits)
    - Lenient tool policies (allowlist-based)
    - Simple output contract
    """
    return WorkspaceRuntimeProfile(
        workspace_id=workspace_id,
        default_mode="execution",  # Prefer execution over discussion

        # Interaction Budget: Higher limits for fast iteration
        interaction_budget=InteractionBudget(
            max_questions_per_turn=0,  # No questions, assume defaults
            assume_defaults=True,  # Assume defaults (Cursor-style)
            require_assumptions_list=True  # List assumptions
        ),

        # Output Contract: Simple and fast
        output_contract=OutputContract(
            coding_style=CodingStyle.PATCH_FIRST,  # Patch first (Cursor-style)
            writing_style=WritingStyle.DRAFT_FIRST,  # Draft first
            minimize_explanation=True,  # Less talk, more action
            show_rationale_level=RationaleLevel.NONE,  # No explanation
            include_decision_log=False  # No decision log
        ),

        # Confirmation Policy: Minimal (only external writes)
        confirmation_policy=ConfirmationPolicy(
            confirm_external_write=True,
            confirm_soft_write=False,
            auto_read=True,
            require_explicit_confirm=False
        ),

        # Tool Policy: Lenient (allowlist-based)
        tool_policy=ToolPolicy(
            allowlist=None,  # Allow all by default
            denylist=None,  # No denylist
            require_approval_for_capabilities=["destructive"],  # Only destructive tools
            max_tool_call_chain=10  # Higher limit for complex workflows
        ),

        # Loop Budget: Higher limits for fast iteration
        loop_budget=LoopBudget(
            max_iterations=20,
            max_turns=50,
            max_steps=100,
            max_tool_calls=50
        ),

        # Stop Conditions: Minimal requirements
        stop_conditions=StopConditions(
            definition_of_done=None,  # No strict definition of done
            max_errors=5,
            max_retries=3
        ),

        # Quality Gates: Minimal checks
        quality_gates=QualityGates(
            require_lint=False,
            require_tests=False,
            require_docs=False,
            require_changelist=False,
            require_rollback_plan=False,
            require_citations=False
        ),

        # Topology: Loop (for iterative development)
        topology_routing=TopologyRouting(
            default_pattern="loop",
            agent_routing_rules={}
        )
    )


def create_research_preset(workspace_id: str) -> WorkspaceRuntimeProfile:
    """
    Create Research preset template

    Characteristics:
    - Detailed output (structured, with reasoning)
    - Citation requirements
    - Complete decision logs
    - Moderate confirmation policies
    """
    return WorkspaceRuntimeProfile(
        workspace_id=workspace_id,
        default_mode="hybrid",  # Balance discussion and execution

        # Interaction Budget: Moderate limits
        interaction_budget=InteractionBudget(
            max_questions_per_turn=2,  # Allow some questions
            assume_defaults=False,  # Don't assume defaults
            require_assumptions_list=True  # Require assumptions list
        ),

        # Output Contract: Detailed and structured
        output_contract=OutputContract(
            coding_style=CodingStyle.EXPLAIN_FIRST,  # Explain before code
            writing_style=WritingStyle.BOTH,  # Both structure and draft
            minimize_explanation=False,  # Detailed explanations
            show_rationale_level=RationaleLevel.DETAILED,  # Full decision log
            include_decision_log=True  # Include decision log for research
        ),

        # Confirmation Policy: Moderate (external writes only)
        confirmation_policy=ConfirmationPolicy(
            confirm_external_write=True,
            confirm_soft_write=False,
            auto_read=True,
            require_explicit_confirm=False
        ),

        # Tool Policy: Moderate (allowlist for research tools)
        tool_policy=ToolPolicy(
            allowlist=None,  # Allow all by default
            denylist=["destructive"],  # Deny destructive tools
            require_approval_for_capabilities=["external_write"],
            max_tool_call_chain=8
        ),

        # Loop Budget: Moderate limits
        loop_budget=LoopBudget(
            max_iterations=15,
            max_turns=30,
            max_steps=60,
            max_tool_calls=40
        ),

        # Stop Conditions: Moderate requirements
        stop_conditions=StopConditions(
            definition_of_done=["docs updated"],  # Require documentation
            max_errors=3,
            max_retries=2
        ),

        # Quality Gates: Research-focused checks
        quality_gates=QualityGates(
            require_lint=True,
            require_tests=False,  # Tests not always needed for research
            require_docs=True,  # Documentation is important
            require_changelist=True,
            require_rollback_plan=False,
            require_citations=True  # Citations are critical for research
        ),

        # Topology: Sequential (for structured research workflow)
        topology_routing=TopologyRouting(
            default_pattern="sequential",
            agent_routing_rules={}
        )
    )


def get_preset_templates() -> dict:
    """
    Get all preset templates

    Returns:
        Dictionary mapping preset names to creation functions
    """
    return {
        "security": create_security_preset,
        "agile": create_agile_preset,
        "research": create_research_preset
    }


def get_preset_names() -> list:
    """Get list of preset template names"""
    return list(get_preset_templates().keys())


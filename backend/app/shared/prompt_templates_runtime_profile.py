"""Runtime profile prompt templates."""

from typing import Optional

from ..models.workspace_runtime_profile import (
    WorkspaceRuntimeProfile,
    InteractionBudget,
    OutputContract,
    ConfirmationPolicy,
    RationaleLevel,
    CodingStyle,
    WritingStyle,
    ConfirmationFormat,
    LoopBudget,
    StopConditions,
    QualityGates,
    SharedStatePolicy,
    RecoveryPolicy,
)


def build_interaction_budget_prompt(interaction_budget: InteractionBudget) -> str:
    """
    Build interaction budget prompt section

    Args:
        interaction_budget: InteractionBudget configuration

    Returns:
        Interaction budget prompt section
    """
    sections = []

    if interaction_budget.max_questions_per_turn == 0:
        sections.append("**No Questions Policy:** Do NOT ask questions. Make assumptions and proceed.")
        if interaction_budget.require_assumptions_list:
            sections.append("**Required:** When making assumptions, explicitly list them in an `assumptions[]` array in your response.")
    elif interaction_budget.max_questions_per_turn == 1:
        sections.append("**Question Limit:** Ask at most 1 question per turn. Be concise.")
    elif interaction_budget.max_questions_per_turn <= 3:
        sections.append(f"**Question Limit:** Ask at most {interaction_budget.max_questions_per_turn} questions per turn.")
    else:
        sections.append(f"**Question Limit:** Ask at most {interaction_budget.max_questions_per_turn} questions per turn (use sparingly).")

    if interaction_budget.assume_defaults:
        sections.append("**Assume Defaults:** When parameters are missing, use sensible defaults instead of asking.")

    return "\n".join(sections)


def build_output_contract_prompt(output_contract: OutputContract) -> str:
    """
    Build output contract prompt section

    Args:
        output_contract: OutputContract configuration

    Returns:
        Output contract prompt section
    """
    sections = []

    coding_style_map = {
        CodingStyle.PATCH_FIRST: "**Coding Style: Patch-First** - Show code changes directly (Cursor-style). Minimize explanation.",
        CodingStyle.EXPLAIN_FIRST: "**Coding Style: Explain-First** - Explain the approach before showing code.",
        CodingStyle.CODE_ONLY: "**Coding Style: Code-Only** - Show code only, minimal explanation."
    }
    if output_contract.coding_style in coding_style_map:
        sections.append(coding_style_map[output_contract.coding_style])

    writing_style_map = {
        WritingStyle.STRUCTURE_FIRST: "**Writing Style: Structure-First** - Show outline/structure before writing full content.",
        WritingStyle.DRAFT_FIRST: "**Writing Style: Draft-First** - Write full draft directly, refine later.",
        WritingStyle.BOTH: "**Writing Style: Both** - Show structure, then write full draft."
    }
    if output_contract.writing_style in writing_style_map:
        sections.append(writing_style_map[output_contract.writing_style])

    if output_contract.minimize_explanation:
        sections.append("**Minimize Explanation:** Less talk, more action. Focus on results, not process.")

    rationale_map = {
        RationaleLevel.NONE: "**Rationale: None** - Do not explain your reasoning.",
        RationaleLevel.BRIEF: "**Rationale: Brief** - Briefly explain key decisions (1-2 sentences).",
        RationaleLevel.DETAILED: "**Rationale: Detailed** - Explain your reasoning in detail."
    }
    if output_contract.show_rationale_level in rationale_map:
        sections.append(rationale_map[output_contract.show_rationale_level])

    if output_contract.include_decision_log:
        sections.append("**Decision Log:** Include assumptions, risks, and next steps in your response.")

    return "\n".join(sections)


def build_confirmation_policy_prompt(confirmation_policy: ConfirmationPolicy) -> str:
    """
    Build confirmation policy prompt section

    Args:
        confirmation_policy: ConfirmationPolicy configuration

    Returns:
        Confirmation policy prompt section
    """
    sections = []

    if confirmation_policy.auto_read:
        sections.append("**Auto-Read:** Read-only operations execute automatically (no confirmation needed).")
    else:
        sections.append("**Read Operations:** Read operations require confirmation.")

    if confirmation_policy.confirm_soft_write:
        sections.append("**Soft Write:** Internal state changes require confirmation.")
    else:
        sections.append("**Soft Write:** Internal state changes execute automatically.")

    if confirmation_policy.confirm_external_write:
        sections.append("**External Write:** External system changes require explicit confirmation.")
    else:
        sections.append("**External Write:** External system changes execute automatically (use with caution).")

    format_map = {
        ConfirmationFormat.LIST_CHANGES: "**Confirmation Format:** List all changes clearly, then wait for user confirmation.",
        ConfirmationFormat.SUMMARY: "**Confirmation Format:** Provide a summary of changes, then wait for confirmation.",
        ConfirmationFormat.DETAILED: "**Confirmation Format:** Provide detailed explanation of changes, then wait for confirmation."
    }
    if confirmation_policy.confirmation_format in format_map:
        sections.append(format_map[confirmation_policy.confirmation_format])

    if confirmation_policy.require_explicit_confirm:
        sections.append("**Explicit Confirmation Required:** Do not proceed until user explicitly confirms.")

    return "\n".join(sections)


def build_loop_budget_prompt(loop_budget: LoopBudget) -> str:
    """
    Build loop budget prompt section (Phase 2)

    Args:
        loop_budget: LoopBudget configuration

    Returns:
        Loop budget prompt section
    """
    sections = []

    sections.append(f"**Max Iterations:** Maximum {loop_budget.max_iterations} iterations for loop-based agents.")
    sections.append(f"**Max Turns:** Maximum {loop_budget.max_turns} conversation turns per session.")
    sections.append(f"**Max Steps:** Maximum {loop_budget.max_steps} execution steps.")
    sections.append(f"**Max Tool Calls:** Maximum {loop_budget.max_tool_calls} tool calls per execution.")

    if loop_budget.token_budget:
        sections.append(f"**Token Budget:** {loop_budget.token_budget} tokens maximum.")

    if loop_budget.cost_budget:
        sections.append(f"**Cost Budget:** ${loop_budget.cost_budget:.2f} USD maximum.")

    if loop_budget.time_budget_seconds:
        sections.append(f"**Time Budget:** {loop_budget.time_budget_seconds} seconds maximum.")

    return "\n".join(sections)


def build_stop_conditions_prompt(stop_conditions: StopConditions) -> str:
    """
    Build stop conditions prompt section (Phase 2)

    Args:
        stop_conditions: StopConditions configuration

    Returns:
        Stop conditions prompt section
    """
    sections = []

    if stop_conditions.definition_of_done:
        done_criteria = ", ".join(stop_conditions.definition_of_done)
        sections.append(f"**Definition of Done:** {done_criteria}")

    if stop_conditions.early_stop_on_success:
        sections.append("**Early Stop:** Stop immediately when success criteria are met.")

    sections.append(f"**Max Retries:** Maximum {stop_conditions.max_retries} retry attempts on failure.")
    sections.append(f"**Max Errors:** Stop after {stop_conditions.max_errors} errors.")

    if stop_conditions.require_critic_agreement:
        sections.append("**Critic Agreement:** Require critic agent agreement before stopping.")

    return "\n".join(sections)


def build_quality_gates_prompt(quality_gates: QualityGates) -> str:
    """
    Build quality gates prompt section (Phase 2)

    Args:
        quality_gates: QualityGates configuration

    Returns:
        Quality gates prompt section
    """
    sections = []

    if quality_gates.require_lint:
        sections.append("**Lint Check:** Code must pass linting before completion.")

    if quality_gates.require_tests:
        sections.append("**Tests:** Tests must pass before completion.")

    if quality_gates.require_docs:
        sections.append("**Documentation:** Documentation must be updated before completion.")

    if quality_gates.require_changelist:
        sections.append("**Change List:** Must provide change list before external writes.")

    if quality_gates.require_rollback_plan:
        sections.append("**Rollback Plan:** Must provide rollback plan for high-risk operations.")

    if quality_gates.require_citations:
        sections.append("**Citations:** Must include source citations in output.")
        if quality_gates.citation_template:
            sections.append(f"**Citation Template:**\n{quality_gates.citation_template}")

    return "\n".join(sections)


def build_shared_state_policy_prompt(shared_state_policy: SharedStatePolicy) -> str:
    """
    Build shared state policy prompt section (Phase 2)

    Args:
        shared_state_policy: SharedStatePolicy configuration

    Returns:
        Shared state policy prompt section
    """
    sections = []

    if shared_state_policy.memory_event_types:
        event_types = ", ".join(shared_state_policy.memory_event_types)
        sections.append(f"**Memory Events:** Write these event types to long-term memory: {event_types}.")

    if shared_state_policy.redact_fields:
        redact_fields = ", ".join(shared_state_policy.redact_fields)
        sections.append(f"**Redact Fields:** Redact these fields before writing to memory: {redact_fields}.")

    if shared_state_policy.summarize_on_turn_count:
        sections.append(f"**Summarize on Turns:** Summarize context after {shared_state_policy.summarize_on_turn_count} turns.")

    if shared_state_policy.summarize_on_token_count:
        sections.append(f"**Summarize on Tokens:** Summarize context after {shared_state_policy.summarize_on_token_count} tokens.")

    if shared_state_policy.switch_rag_on_topic_change:
        sections.append("**RAG Switching:** Switch RAG source when topic changes.")

    return "\n".join(sections)


def build_recovery_policy_prompt(recovery_policy: RecoveryPolicy) -> str:
    """
    Build recovery policy prompt section (Phase 2)

    Args:
        recovery_policy: RecoveryPolicy configuration

    Returns:
        Recovery policy prompt section
    """
    sections = []

    if recovery_policy.retry_on_failure:
        strategy_map = {
            "immediate": "Retry immediately on failure.",
            "exponential_backoff": "Retry with exponential backoff on failure.",
            "ask_user": "Ask user before retrying on failure."
        }
        sections.append(f"**Retry Strategy:** {strategy_map.get(recovery_policy.retry_strategy, 'Retry on failure.')}")

    if recovery_policy.fallback_on_error:
        fallback_map = {
            "qa_only": "Fallback to QA-only mode on error.",
            "readonly": "Fallback to read-only operations on error.",
            "ask_user": "Ask user for guidance on error."
        }
        sections.append(f"**Fallback Mode:** {fallback_map.get(recovery_policy.fallback_mode, 'Fallback on error.')}")

    if recovery_policy.escalate_to_human_on:
        escalate_ops = ", ".join(recovery_policy.escalate_to_human_on)
        sections.append(f"**Escalate to Human:** Escalate to human on these operations: {escalate_ops}.")

    return "\n".join(sections)


def build_runtime_profile_prompt(
    runtime_profile: WorkspaceRuntimeProfile,
    preferred_language: Optional[str] = None
) -> str:
    """
    Build complete runtime profile prompt section

    This prompt section defines execution contracts and operational postures
    that are more granular than execution_mode.

    Args:
        runtime_profile: WorkspaceRuntimeProfile configuration
        preferred_language: User's preferred language (for localization)

    Returns:
        Complete runtime profile prompt section
    """
    runtime_profile.ensure_phase2_fields()

    interaction_section = build_interaction_budget_prompt(runtime_profile.interaction_budget)
    output_section = build_output_contract_prompt(runtime_profile.output_contract)
    confirmation_section = build_confirmation_policy_prompt(runtime_profile.confirmation_policy)

    loop_budget_section = build_loop_budget_prompt(runtime_profile.loop_budget)
    stop_conditions_section = build_stop_conditions_prompt(runtime_profile.stop_conditions)
    quality_gates_section = build_quality_gates_prompt(runtime_profile.quality_gates)
    shared_state_section = build_shared_state_policy_prompt(runtime_profile.shared_state_policy)
    recovery_section = build_recovery_policy_prompt(runtime_profile.recovery_policy)

    runtime_profile_prompt = f"""[RUNTIME_PROFILE]
**Execution Contract & Operational Posture**

**Interaction Budget:**
{interaction_section}

**Output Contract:**
{output_section}

**Confirmation Policy:**
{confirmation_section}

**Loop Budget (Phase 2):**
{loop_budget_section}

**Stop Conditions (Phase 2):**
{stop_conditions_section}

**Quality Gates (Phase 2):**
{quality_gates_section}

**Shared State Policy (Phase 2):**
{shared_state_section}

**Recovery Policy (Phase 2):**
{recovery_section}
[/RUNTIME_PROFILE]"""

    return runtime_profile_prompt

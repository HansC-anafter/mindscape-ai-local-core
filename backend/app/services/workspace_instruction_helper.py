"""
Workspace Instruction Helper — Single source of truth.

Formats WorkspaceInstruction / legacy brief into an LLM-injectable text block.
Every LLM path MUST call build_workspace_instruction_block() to guarantee
consistent precedence and observable injection_source logging.

Precedence: instruction(populated fields) > brief > none
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def build_workspace_instruction_block(
    workspace,
    *,
    caller: str = "unknown",
) -> Tuple[str, str]:
    """Build workspace instruction text block.

    Args:
        workspace: Workspace object (must have workspace_blueprint attribute).
        caller: Identifier for the calling path (for observability logs).

    Returns:
        (block_text, injection_source)
        injection_source is one of: "instruction", "brief", "none".
    """
    bp = getattr(workspace, "workspace_blueprint", None) if workspace else None
    if not bp:
        logger.debug(
            "WorkspaceInstruction: injection_source=none, caller=%s, "
            "workspace=%s (no blueprint)",
            caller,
            getattr(workspace, "id", "?") if workspace else "none",
        )
        return "", "none"

    # Priority 1: structured instruction (at least one field populated)
    instr = getattr(bp, "instruction", None)
    if instr and _has_content(instr):
        block = _format_instruction(instr)
        if block:
            logger.info(
                "WorkspaceInstruction: injection_source=instruction, "
                "caller=%s, workspace=%s",
                caller,
                getattr(workspace, "id", "?"),
            )
            return block, "instruction"

    # Priority 2: legacy brief
    brief = getattr(bp, "brief", None)
    if brief:
        block = f"=== Workspace Brief ===\n{brief}\n=== End Brief ==="
        logger.info(
            "WorkspaceInstruction: injection_source=brief, " "caller=%s, workspace=%s",
            caller,
            getattr(workspace, "id", "?"),
        )
        return block, "brief"

    # Priority 3: nothing
    logger.debug(
        "WorkspaceInstruction: injection_source=none, caller=%s, " "workspace=%s",
        caller,
        getattr(workspace, "id", "?") if workspace else "none",
    )
    return "", "none"


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _has_content(instr) -> bool:
    """Check if instruction has at least one populated field."""
    return any(
        [
            getattr(instr, "persona", None),
            getattr(instr, "goals", None),
            getattr(instr, "anti_goals", None),
            getattr(instr, "style_rules", None),
            getattr(instr, "domain_context", None),
        ]
    )


def _format_instruction(instr) -> str:
    """Format WorkspaceInstruction into a delimited text block."""
    parts = []
    if instr.persona:
        parts.append(f"Persona: {instr.persona}")
    if instr.goals:
        parts.append("Goals:\n" + "\n".join(f"  - {g}" for g in instr.goals))
    if instr.anti_goals:
        parts.append(
            "Anti-goals (DO NOT):\n" + "\n".join(f"  - {a}" for a in instr.anti_goals)
        )
    if instr.style_rules:
        parts.append("Style:\n" + "\n".join(f"  - {s}" for s in instr.style_rules))
    if instr.domain_context:
        parts.append(f"Domain context:\n{instr.domain_context}")
    if not parts:
        return ""
    return (
        "=== Workspace Instruction ===\n"
        + "\n".join(parts)
        + "\n=== End Instruction ==="
    )

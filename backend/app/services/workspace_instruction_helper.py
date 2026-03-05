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
    exclude_fields: tuple = (),
    fallback_to_brief: bool = True,
    raw_body: bool = False,
) -> Tuple[str, str]:
    """Build workspace instruction text block.

    Args:
        workspace: Workspace object (must have workspace_blueprint attribute).
        caller: Identifier for the calling path (for observability logs).
        exclude_fields: Field names to omit from formatted output
            (e.g. ("persona", "anti_goals") for meeting callers).
        fallback_to_brief: If False, skip legacy brief entirely.
            Meeting callers set this to False to prevent unfiltered
            persona content from leaking through the brief path.
        raw_body: If True, return plain text without === delimiters.
            Useful when the caller wraps the output in its own delimiters.

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
        block = _format_instruction(
            instr, exclude_fields=exclude_fields, raw_body=raw_body
        )
        if block:
            logger.info(
                "WorkspaceInstruction: injection_source=instruction, "
                "caller=%s, workspace=%s",
                caller,
                getattr(workspace, "id", "?"),
            )
            return block, "instruction"

    # Priority 2: legacy brief (skipped when fallback_to_brief=False)
    if fallback_to_brief:
        brief = getattr(bp, "brief", None)
        if brief:
            if raw_body:
                block = brief
            else:
                block = f"=== Workspace Brief ===\n{brief}\n=== End Brief ==="
            logger.info(
                "WorkspaceInstruction: injection_source=brief, "
                "caller=%s, workspace=%s",
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


def _format_instruction(instr, exclude_fields=(), raw_body=False) -> str:
    """Format WorkspaceInstruction into a text block.

    Args:
        instr: WorkspaceInstruction object.
        exclude_fields: Field names to skip (e.g. "persona", "anti_goals").
        raw_body: If True, omit === delimiters and return plain text.
    """
    parts = []
    if getattr(instr, "persona", None) and "persona" not in exclude_fields:
        parts.append(f"Persona: {instr.persona}")
    if getattr(instr, "goals", None) and "goals" not in exclude_fields:
        parts.append("Goals:\n" + "\n".join(f"  - {g}" for g in instr.goals))
    if getattr(instr, "anti_goals", None) and "anti_goals" not in exclude_fields:
        parts.append(
            "Anti-goals (DO NOT):\n" + "\n".join(f"  - {a}" for a in instr.anti_goals)
        )
    if getattr(instr, "style_rules", None) and "style_rules" not in exclude_fields:
        parts.append("Style:\n" + "\n".join(f"  - {s}" for s in instr.style_rules))
    if (
        getattr(instr, "domain_context", None)
        and "domain_context" not in exclude_fields
    ):
        parts.append(f"Domain context:\n{instr.domain_context}")
    if not parts:
        return ""
    if raw_body:
        return "\n".join(parts)
    return (
        "=== Workspace Instruction ===\n"
        + "\n".join(parts)
        + "\n=== End Instruction ==="
    )

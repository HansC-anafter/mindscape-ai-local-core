"""Prompt formatting helpers for workspace welcome message generation."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

_ZH_ACTION_HOME_DRAFT = "\u751f\u6210\u9996\u9801\u8349\u7a3f"
_ZH_CAN_START = "\u53ef\u4ee5\u958b\u59cb"
_ZH_WITH_CODE = "\u542b\u4ee3\u78bc"
_ZH_ANALYZE_FILES = "\u5206\u6790\u6a94\u6848"
_ZH_SELECT_TARGET = "\u9078\u64c7\u76ee\u6a19"
_ZH_RUN_SPECIFIC = "\u57f7\u884c\u7279\u5b9a"
_ZH_VIEW_EXAMPLES = "\u6aa2\u8996\u7bc4\u4f8b"
_ZH_CLEAR_ACTIONS = "\u660e\u78ba\u884c\u70ba"
_ZH_AMBIGUOUS = "\u6a21\u7cca"
_ZH_FILLER = "\u586b\u5145"
_ZH_TERM = "\u8a9e"
_ZH_MAYBE = "\u6216\u8a31"
_ZH_AVOID_EMPTY_GOALS = "\u907f\u514d\u7a7a\u6cdb\u76ee\u6a19"
_ZH_ALSO = "\u4e5f"

_LIST_MARKER_CHARS = "- *\u20221234567890. "
_BANNED_SUGGESTION_PATTERNS = (
    re.compile(
        rf"^{re.escape(_ZH_MAYBE)}(?:{re.escape(_ZH_ALSO)})?"
        rf"{re.escape(_ZH_CAN_START)}",
        re.IGNORECASE,
    ),
    re.compile(r"^maybe\s*(we)?\s*can\s*start", re.IGNORECASE),
    re.compile(rf"^{re.escape(_ZH_CAN_START)}", re.IGNORECASE),
    re.compile(r"^start\s*now\b", re.IGNORECASE),
    re.compile(r"^let'?s\s*start", re.IGNORECASE),
)


def _workspace_value(workspace: Any, field: str, fallback: str) -> str:
    return str(getattr(workspace, field, None) or fallback)


def _format_active_intents(
    active_intents: Sequence[Mapping[str, str]],
    empty_text: str,
) -> str:
    if not active_intents:
        return empty_text
    return "\n".join(
        f"- {intent['title']}: {intent['description']}" for intent in active_intents
    )


def _format_playbooks(
    available_playbooks: Sequence[Mapping[str, Any]],
    empty_text: str,
    *,
    limit: int,
) -> str:
    if not available_playbooks:
        return empty_text
    return "\n".join(
        (
            f"- {playbook['name']} ({playbook['playbook_code']}): "
            f"{playbook['description']}"
        )
        for playbook in available_playbooks[:limit]
    )


def build_suggestions_system_prompt(
    *,
    target_language: str,
    locale: str,
    language_instruction: str,
) -> str:
    return f"""You are an onboarding coach for a new workspace. Give the user concrete, ready-to-click starting actions.

Guidelines (must follow all):
- Output 2-4 concise, actionable suggestions (each <= 15 words) in {target_language} ({locale}).
- Lead with a verb and be specific (e.g., \"{_ZH_ACTION_HOME_DRAFT}\" rather than \"{_ZH_CAN_START}\").
- Prefer referencing available playbooks / capabilities explicitly ({_ZH_WITH_CODE}) when relevant.
- If useful, mention uploading/{_ZH_ANALYZE_FILES}\u3001{_ZH_SELECT_TARGET}\u3001{_ZH_RUN_SPECIFIC} playbook\u3001{_ZH_VIEW_EXAMPLES}\u7b49{_ZH_CLEAR_ACTIONS}\u3002
- Avoid{_ZH_AMBIGUOUS}/{_ZH_FILLER}{_ZH_TERM}\u300c{_ZH_MAYBE}\u300d\u300cmaybe\u300d\u300clet's start\u300d\u300c{_ZH_CAN_START}\u300d\u7b49\uff1b{_ZH_AVOID_EMPTY_GOALS}\u3002
- No numbered list markers; one suggestion per line.

**CRITICAL:**
{language_instruction}
If nothing relevant, return nothing."""


def build_suggestions_user_prompt(
    *,
    workspace: Any,
    active_intents: Sequence[Mapping[str, str]],
    available_playbooks: Sequence[Mapping[str, Any]],
    mindscape_context: str,
    target_language: str,
) -> str:
    intents_text = _format_active_intents(active_intents, "No active intents yet")
    playbooks_text = _format_playbooks(
        available_playbooks,
        "No specific playbooks detected",
        limit=5,
    )
    return f"""Workspace Context:
- Title: {_workspace_value(workspace, "title", "Untitled workspace")}
- Description: {_workspace_value(workspace, "description", "No description")}
- Mode: {_workspace_value(workspace, "mode", "Not specified")}

Active Goals/Intents:
{intents_text}

Available Playbooks (include code for actionable refs):
{playbooks_text}

Context: {mindscape_context or "This is a new workspace"}

Produce 2-4 actionable starter steps (one per line, no numbering), each <= 15 words, verb-led, specific, in {target_language}. If nothing relevant, return empty."""


def sanitize_suggestions_text(suggestions_text: str, *, limit: int = 4) -> list[str]:
    suggestions: list[str] = []
    for raw_line in suggestions_text.split("\n"):
        line = raw_line.strip().lstrip(_LIST_MARKER_CHARS).strip()
        if not line or len(line) <= 5:
            continue
        if any(pattern.search(line) for pattern in _BANNED_SUGGESTION_PATTERNS):
            continue
        suggestions.append(line)

    seen: set[str] = set()
    unique_suggestions: list[str] = []
    for suggestion in suggestions:
        suggestion_lower = suggestion.lower().strip()
        if suggestion_lower and suggestion_lower not in seen:
            seen.add(suggestion_lower)
            unique_suggestions.append(suggestion)
    return unique_suggestions[:limit]


def build_welcome_system_prompt(
    *,
    workspace: Any,
    locale: str,
    target_language: str,
    language_instruction: str,
) -> str:
    return f"""You are a helpful AI assistant welcoming a user to their new workspace \"{_workspace_value(workspace, "title", "Untitled workspace")}\".

Generate a warm, personalized welcome message that:
1. Welcomes the user to the workspace by name
2. Explains what this workspace is for (based on workspace title and description)
3. Mentions available capabilities/playbooks that might be useful
4. References any active intents/goals if they exist
5. Provides clear next steps and guidance
6. Is conversational, friendly, and encouraging

**CRITICAL LANGUAGE REQUIREMENT:**
{language_instruction}
The workspace locale is {locale} ({target_language}), so you MUST respond in {target_language} only.
Do NOT mix languages. Do NOT use English if the locale is not 'en'.

Keep it concise but informative (2-4 paragraphs)."""


def build_welcome_user_prompt(
    *,
    workspace: Any,
    available_playbooks: Sequence[Mapping[str, Any]],
    active_intents: Sequence[Mapping[str, str]],
    context: str,
    target_language: str,
    locale: str,
) -> str:
    playbooks_text = _format_playbooks(
        available_playbooks,
        "No specific playbooks configured yet",
        limit=10,
    )
    intents_text = _format_active_intents(
        active_intents,
        "No active intents yet - this is a fresh start!",
    )
    return f"""Workspace Information:
- Title: {_workspace_value(workspace, "title", "Untitled workspace")}
- Description: {_workspace_value(workspace, "description", "No description")}
- Mode: {_workspace_value(workspace, "mode", "Not specified")}

Available Capabilities/Playbooks:
{playbooks_text}

Active Goals/Intents:
{intents_text}

Context:
{context if context else "This is a brand new workspace with no history yet."}

Generate a personalized welcome message for this workspace. Remember to respond in {target_language} ({locale}) as specified in the system prompt."""

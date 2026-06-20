"""Pure helpers for core LLM direct Codex CLI execution."""

from __future__ import annotations

import os
from typing import Any, Optional

from ...shared.llm_utils import extract_json_from_text


def codex_model_hint(model: Optional[str]) -> Optional[str]:
    candidate = str(model or "").strip()
    if not candidate:
        return None
    lowered = candidate.lower()
    if lowered.startswith(("gpt-", "o", "codex")):
        return candidate
    return None


def build_codex_cli_command(
    *,
    binary: str,
    last_message_path: str,
    task: str,
    model: Optional[str],
) -> list[str]:
    cmd = [
        binary,
        "-c",
        'model_reasoning_effort="high"',
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--output-last-message",
        last_message_path,
    ]
    model_hint = codex_model_hint(model)
    if model_hint:
        cmd.extend(["--model", model_hint])
    cmd.append(task)
    return cmd


def merge_codex_env(extra_env: Optional[dict[str, Any]]) -> dict[str, str]:
    env = os.environ.copy()
    if extra_env:
        env.update(
            {
                str(key): str(value)
                for key, value in extra_env.items()
                if value is not None and str(value) != ""
            }
        )
    return env


def codex_pool_wait_attempt_count() -> int:
    raw = os.environ.get("MINDSCAPE_CODEX_POOL_WAIT_ATTEMPTS", "6").strip()
    try:
        return max(1, min(12, int(raw)))
    except ValueError:
        return 6


def resolve_codex_stall_timeout(
    *,
    raw_value: str,
    default_timeout: float,
) -> float:
    try:
        return max(5.0, float(raw_value))
    except ValueError:
        return default_timeout


def parse_codex_success_output(
    *,
    output_text: str,
    response_format: str,
) -> Any:
    text = str(output_text or "").strip()
    if response_format == "json":
        parsed = extract_json_from_text(text)
        if parsed is None:
            raise ValueError("codex_cli did not return valid JSON for core_llm_call")
        return parsed
    return text


def codex_error_text_from_result(result: Any) -> str:
    return (
        result.synthesized_error
        or result.combined_output
        or result.stderr_text
        or result.output_text
        or "unknown error"
    ).strip()

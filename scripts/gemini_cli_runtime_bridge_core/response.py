import json


def _looks_like_auth_error(stderr_text: str) -> bool:
    """Detect auth-related errors in subprocess stderr."""
    if not stderr_text:
        return False
    lower = stderr_text.lower()
    auth_patterns = (
        "401",
        "403",
        "unauthenticated",
        "unauthorized",
        "token expired",
        "invalid credentials",
        "permission denied",
        "access denied",
        "auth not set",
    )
    return any(p in lower for p in auth_patterns)


def _looks_like_quota_error(text: str) -> bool:
    """Detect quota/rate-limit errors (429 RESOURCE_EXHAUSTED)."""
    if not text:
        return False
    lower = text.lower()
    quota_patterns = (
        "429",
        "resource_exhausted",
        "resource exhausted",
        "quota exceeded",
        "rate limit",
        "too many requests",
    )
    return any(p in lower for p in quota_patterns)


def _extract_response(raw_stdout: str) -> tuple[str, str | None]:
    """Extract the final response and error from Gemini CLI JSON output.

    When using --output-format json, the CLI returns:
        Success: {"session_id": "...", "response": "final answer", "stats": {...}}
        Error:   {"error": {"type": "...", "message": "...", "code": "..."}}

    When response is empty but tool calls succeeded, builds a summary
    from the stats instead of falling back to the raw JSON dump.

    Returns:
        (response_text, json_error_msg) - json_error_msg is None on success
    """
    if not raw_stdout:
        return (raw_stdout, None)
    try:
        parsed = json.loads(raw_stdout)
        error = parsed.get("error")
        error_msg = None
        if isinstance(error, dict):
            error_msg = error.get("message") or str(error)
        elif isinstance(error, str):
            error_msg = error

        response = parsed.get("response", "") or ""
        if response:
            return (response, error_msg)

        stats = parsed.get("stats", {})
        tool_stats = stats.get("tools", {})
        total_calls = tool_stats.get("totalCalls", 0)
        total_success = tool_stats.get("totalSuccess", 0)

        if total_calls > 0 and total_success > 0:
            tool_lines = []
            by_name = tool_stats.get("byName", {})
            for name, info in by_name.items():
                calls = info.get("count", 0)
                ok = info.get("success", 0)
                fail = info.get("fail", 0)
                tool_lines.append(f"- {name}: {calls} calls ({ok} ok, {fail} fail)")
            summary_parts = [
                f"Agent completed {total_calls} tool call(s) "
                f"({total_success} succeeded) but did not produce "
                f"a final text response.",
            ]
            if tool_lines:
                summary_parts.append("Tool usage:")
                summary_parts.extend(tool_lines)
            summary_parts.append(
                "\nPlease re-run the query or ask a follow-up question "
                "to get a text summary of the results."
            )
            return ("\n".join(summary_parts), error_msg)

        return ("", error_msg)
    except (json.JSONDecodeError, TypeError):
        return (raw_stdout, None)

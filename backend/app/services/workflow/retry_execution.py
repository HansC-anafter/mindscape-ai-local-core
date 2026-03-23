"""Retry-loop helpers for workflow step execution."""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)


async def execute_step_with_retry(
    *,
    step: Any,
    workflow_context: Dict[str, Any],
    previous_results: Dict[str, Dict[str, Any]],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    profile_id: Optional[str],
    project_id: Optional[str],
    step_index: int,
    execute_workflow_step_fn: Callable[..., Awaitable[Dict[str, Any]]],
    get_default_retry_policy_fn: Callable[[Any], Any],
    calculate_retry_delay_fn: Callable[[int, Any], float],
    classify_error_fn: Callable[[str], str],
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Dict[str, Any]:
    """Execute a workflow step with retry handling."""
    retry_policy = step.retry_policy or get_default_retry_policy_fn(step.kind)

    last_error = None
    for attempt in range(retry_policy.max_retries + 1):
        try:
            if attempt > 0:
                delay = calculate_retry_delay_fn(attempt, retry_policy)
                logger.info(
                    "Retrying step %s (attempt %s/%s) after %ss",
                    step.playbook_code,
                    attempt + 1,
                    retry_policy.max_retries + 1,
                    delay,
                )
                await sleep_fn(delay)

            result = await execute_workflow_step_fn(
                step,
                workflow_context,
                previous_results,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
                step_index=step_index,
            )

            if result.get("status") == "completed":
                if attempt > 0:
                    logger.info(
                        "Step %s succeeded after %s retries",
                        step.playbook_code,
                        attempt,
                    )
                return result

            last_error = result.get("error", "Unknown error")
            error_type = classify_error_fn(last_error)
            if (
                retry_policy.retryable_errors
                and error_type not in retry_policy.retryable_errors
            ):
                logger.warning(
                    "Error type %s is not retryable for step %s",
                    error_type,
                    step.playbook_code,
                )
                return result
        except Exception as exc:
            last_error = str(exc)
            error_type = classify_error_fn(last_error)
            logger.warning(
                "Step %s failed (attempt %s/%s): %s",
                step.playbook_code,
                attempt + 1,
                retry_policy.max_retries + 1,
                exc,
            )

            if (
                retry_policy.retryable_errors
                and error_type not in retry_policy.retryable_errors
            ):
                logger.warning(
                    "Error type %s is not retryable for step %s",
                    error_type,
                    step.playbook_code,
                )
                return {
                    "status": "error",
                    "error": last_error,
                    "error_type": error_type,
                    "attempts": attempt + 1,
                    "retries_exhausted": False,
                }

            if attempt < retry_policy.max_retries:
                continue

            return {
                "status": "error",
                "error": last_error,
                "error_type": error_type,
                "attempts": attempt + 1,
                "retries_exhausted": True,
            }

    return {
        "status": "error",
        "error": last_error or "Unknown error",
        "attempts": retry_policy.max_retries + 1,
        "retries_exhausted": True,
    }

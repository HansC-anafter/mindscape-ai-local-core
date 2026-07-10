"""Single decision table for runner resource-related process failures."""

from __future__ import annotations

from dataclasses import dataclass

RESOURCE_BLOCK_REASONS = frozenset(
    {
        "resource_exhausted",
        "unclassified_sigkill",
        "resource_ownership_lost",
    }
)


@dataclass(frozen=True)
class ResourceFailureDecision:
    action: str
    blocked_reason: str | None = None
    consumes_workflow_retry: bool = False
    auto_requeue: bool = False


def decide_resource_failure(
    source: str | None,
    *,
    resource_contract_available: bool = True,
) -> ResourceFailureDecision:
    normalized = str(source or "").strip().lower()
    if normalized == "browser_resource_lease":
        return ResourceFailureDecision(
            action="resource_wait",
            blocked_reason="resource_wait",
            auto_requeue=True,
        )
    if normalized == "runner_cgroup_oom_correlated":
        if not resource_contract_available:
            return ResourceFailureDecision(
                action="normal_retry",
                consumes_workflow_retry=True,
                auto_requeue=True,
            )
        return ResourceFailureDecision(
            action="resource_block",
            blocked_reason="resource_exhausted",
        )
    if normalized in {
        "subprocess_sigkill",
        "unclassified_sigkill",
        "resource_ownership_lost",
    }:
        if (
            normalized != "resource_ownership_lost"
            and not resource_contract_available
        ):
            return ResourceFailureDecision(
                action="normal_retry",
                consumes_workflow_retry=True,
                auto_requeue=True,
            )
        return ResourceFailureDecision(
            action="resource_block",
            blocked_reason=(
                "unclassified_sigkill"
                if normalized == "subprocess_sigkill"
                else normalized
            ),
        )
    return ResourceFailureDecision(
        action="normal_retry",
        consumes_workflow_retry=True,
        auto_requeue=True,
    )


def is_resource_block_reason(reason: str | None) -> bool:
    return str(reason or "").strip().lower() in RESOURCE_BLOCK_REASONS

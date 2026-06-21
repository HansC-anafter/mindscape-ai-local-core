"""External agent preflight helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services.governance.stubs import (
    PlaybookPreflightResult,
    PreflightStatus,
)

logger = logging.getLogger(__name__)


async def check_external_agent_execution(
    preflight: Any,
    agent_id: str,
    task: str,
    workspace: Any,
    context: Optional[Dict[str, Any]] = None,
) -> PlaybookPreflightResult:
    """Perform preflight checks before external agent execution."""
    playbook_code = f"agent:{agent_id}"
    context = context or {}

    try:
        governance_mode = preflight.settings_store.get("governance.mode", "strict")
        is_strict_mode = governance_mode == "strict"

        workspace_id = str(getattr(workspace, "id", "") or "").strip() or None
        agent_available, agent_error = await preflight._check_agent_availability(
            agent_id,
            workspace_id=workspace_id,
        )
        if not agent_available:
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.REJECT,
                accepted=False,
                rejection_reason=agent_error
                or f"Agent {agent_id} is not available",
            )

        sandbox_approved, sandbox_issues = preflight._check_sandbox_config(
            agent_id, task, workspace, context
        )
        if not sandbox_approved and is_strict_mode:
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.REJECT,
                accepted=False,
                rejection_reason=f"Sandbox config issue: {sandbox_issues}",
            )
        if not sandbox_approved:
            logger.warning(
                f"[WARNING MODE] Sandbox issue: {sandbox_issues}, allowing execution"
            )

        if task.startswith("[Meeting Agent Turn]"):
            risk_level, risk_reasons = "low", []
        else:
            risk_level, risk_reasons = preflight._assess_task_risk(
                task, workspace, context
            )

        if risk_level == "high":
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.NEED_CLARIFICATION,
                accepted=False,
                clarification_questions=[
                    f"This task has HIGH risk level. Reason: {'; '.join(risk_reasons)}. Proceed?",
                ],
            )
        if risk_level == "critical":
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.REJECT,
                accepted=False,
                rejection_reason=f"Task has CRITICAL risk level: {'; '.join(risk_reasons)}",
            )

        logger.info(
            f"External agent preflight passed: agent={agent_id}, risk={risk_level}"
        )
        return PlaybookPreflightResult(
            playbook_code=playbook_code,
            status=PreflightStatus.ACCEPT,
            accepted=True,
        )

    except Exception as e:
        logger.error(f"External agent preflight failed: {e}", exc_info=True)
        return PlaybookPreflightResult(
            playbook_code=playbook_code,
            status=PreflightStatus.REJECT,
            accepted=False,
            rejection_reason=f"Preflight error: {str(e)}",
        )


async def check_agent_availability(
    agent_id: str,
    workspace_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Check whether the external agent adapter is registered and available."""
    try:
        from backend.app.services.external_agents.core.registry import (
            get_runtime_registry,
        )

        registry = get_runtime_registry()

        if agent_id not in registry.list_agents():
            return False, f"Agent '{agent_id}' is not registered"

        adapter = registry.get_adapter(agent_id)
        if not adapter:
            return False, f"Agent '{agent_id}' adapter not found"

        availability_detail: Dict[str, Any] = {}
        if hasattr(adapter, "get_availability_detail"):
            try:
                availability_detail = adapter.get_availability_detail(
                    workspace_id=workspace_id,
                )
            except TypeError:
                availability_detail = adapter.get_availability_detail()
        if availability_detail:
            is_available = bool(availability_detail.get("available"))
        else:
            is_available = await adapter.is_available(workspace_id=workspace_id)
        if not is_available:
            reason = str(availability_detail.get("reason") or "").strip()
            if reason == "no_ws_client":
                return (
                    False,
                    "No WebSocket client connected. "
                    f"Run scripts/start_cli_bridge.sh --surface {agent_id} "
                    "to connect the host bridge.",
                )
            if reason:
                return (
                    False,
                    f"Agent '{agent_id}' is not available for workspace "
                    f"{workspace_id or 'global'}: {reason}",
                )
            return (
                False,
                f"Agent '{agent_id}' CLI is not available (not installed or not in PATH)",
            )

        return True, None

    except ImportError as e:
        logger.warning(f"Agent registry not available: {e}")
        return False, "External agent system not available"
    except Exception as e:
        logger.error(f"Error checking agent availability: {e}")
        return False, str(e)


def get_bound_runtime_ids(workspace: Any) -> List[str]:
    """Return workspace-bound runtime IDs from model-routing-registry policy."""
    from backend.app.services.executor_routing_policy_service import (
        ExecutorRoutingPolicyService,
    )

    runtime_ids: List[str] = []
    snapshot = ExecutorRoutingPolicyService.extract_workspace_policy_snapshot(workspace)
    primary_runtime = snapshot.get("primary_executor_runtime")
    if isinstance(primary_runtime, str) and primary_runtime.strip():
        runtime_ids.append(primary_runtime.strip())

    surfaces = snapshot.get("surfaces")
    if isinstance(surfaces, dict):
        for surface, entry in surfaces.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("enabled") and surface not in runtime_ids:
                runtime_ids.append(surface)
            preferred_runtime_id = entry.get("preferred_runtime_id")
            if (
                isinstance(preferred_runtime_id, str)
                and preferred_runtime_id.strip()
                and preferred_runtime_id.strip() not in runtime_ids
            ):
                runtime_ids.append(preferred_runtime_id.strip())

    return runtime_ids


def check_sandbox_config(
    agent_id: str,
    task: str,
    workspace: Any,
    context: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Check whether workspace sandbox configuration allows the operation."""
    bound_runtimes = get_bound_runtime_ids(workspace)
    if bound_runtimes and agent_id not in bound_runtimes:
        return (
            False,
            f"Agent '{agent_id}' not in model-route-registry workspace executor route: {bound_runtimes}",
        )

    sandbox_config = getattr(workspace, "sandbox_config", None) or {}

    tool_acquire_policy = sandbox_config.get("tool_acquire_policy", "free")
    if tool_acquire_policy == "blocked":
        tool_keywords = ["install", "npm", "pip", "download", "clone", "fetch"]
        task_lower = task.lower()
        for keyword in tool_keywords:
            if keyword in task_lower:
                return (
                    False,
                    f"Tool acquisition is blocked (matched keyword: {keyword})",
                )

    network_keywords = [
        "fetch",
        "download",
        "api",
        "request",
        "http",
        "curl",
        "wget",
    ]
    task_lower = task.lower()
    involves_network = any(kw in task_lower for kw in network_keywords)

    if involves_network:
        network_allowlist = sandbox_config.get("network_allowlist", [])
        if not network_allowlist:
            logger.debug("Task may involve network, but no allowlist configured")

    return True, None


def assess_task_risk(
    task: str,
    workspace: Any,
    context: Dict[str, Any],
) -> Tuple[str, List[str]]:
    """Assess the risk level of an external agent task."""
    reasons = []
    task_lower = task.lower()

    critical_patterns = [
        ("rm -rf /", "Destructive filesystem operation"),
        ("sudo", "Requires elevated privileges"),
        ("chmod 777", "Insecure permission change"),
        (":(){:|:&};:", "Fork bomb detected"),
        ("mkfs", "Disk formatting detected"),
    ]
    for pattern, reason in critical_patterns:
        if pattern in task_lower:
            reasons.append(reason)
            return "critical", reasons

    high_risk_patterns = [
        ("delete", "Deletion operation"),
        ("remove", "Removal operation"),
        ("drop table", "Database drop"),
        ("truncate", "Data truncation"),
        ("overwrite", "Overwrite operation"),
        ("force push", "Force push to repository"),
        ("--force", "Force flag detected"),
        ("secrets", "Secrets access"),
        ("password", "Password handling"),
        ("credentials", "Credentials handling"),
        ("api_key", "API key handling"),
        ("token", "Token handling"),
        ("刪除", "刪除操作"),
        ("移除", "移除操作"),
        ("清除", "清除操作"),
        ("密碼", "密碼操作"),
        ("密鑰", "密鑰操作"),
        ("憑證", "憑證操作"),
    ]
    for pattern, reason in high_risk_patterns:
        if pattern in task_lower:
            reasons.append(reason)

    if reasons:
        return "high", reasons

    medium_risk_patterns = [
        ("write", "Write operation"),
        ("modify", "Modify operation"),
        ("update", "Update operation"),
        ("change", "Change operation"),
        ("deploy", "Deployment operation"),
        ("publish", "Publishing operation"),
        ("寫", "寫入操作"),
        ("修改", "修改操作"),
        ("更新", "更新操作"),
        ("建立", "建立操作"),
        ("創建", "創建操作"),
        ("部署", "部署操作"),
        ("發布", "發布操作"),
        ("執行", "執行操作"),
        ("安裝", "安裝操作"),
    ]
    for pattern, reason in medium_risk_patterns:
        if pattern in task_lower:
            reasons.append(reason)

    if reasons:
        return "medium", reasons

    return "low", []

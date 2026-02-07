"""
External Agent Tools for Playbook Integration

Provides Playbook-callable tools for executing external agents
within Mindscape's governance layer.

Uses the Agent Registry for pluggable agent discovery.

Usage in Playbook:
    steps:
      - id: execute_moltbot
        tool: external_agent.execute
        inputs:
          agent: moltbot
          task: "Build a landing page for the product"
          allowed_tools: ["file", "web_search"]
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def execute_agent(
    agent: str,
    task: str,
    allowed_tools: Optional[List[str]] = None,
    denied_tools: Optional[List[str]] = None,
    max_duration: int = 300,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a task using a registered external agent.

    This is the primary Playbook tool for external agent execution.
    Uses the Agent Registry for pluggable agent discovery.

    SECURITY: All agent execution is now workspace-bound.
    - workspace_id is REQUIRED
    - sandbox_path is auto-generated within workspace boundaries

    Args:
        agent: Agent name (e.g., 'moltbot', 'autogpt')
        task: The task description for the agent to execute
        allowed_tools: List of allowed tools (default from AGENT.md)
        denied_tools: Additional tools to deny
        max_duration: Maximum execution time in seconds
        context: Mindscape execution context (MUST include workspace_id)

    Returns:
        dict with success, output, duration, execution_trace, error
    """
    import uuid
    from backend.app.services.external_agents import (
        get_agent_registry,
        AgentRequest,
    )
    from backend.app.services.external_agents.core.execution_trace import (
        ExecutionTraceCollector,
    )
    from backend.app.services.external_agents.core.workspace_sandbox_resolver import (
        get_agent_sandbox,
    )
    from backend.app.services.governance.agent_preflight import (
        check_agent_preflight,
    )

    # Extract context
    ctx = context or {}

    # SECURITY: workspace_id is REQUIRED
    workspace_id = ctx.get("workspace_id")
    if not workspace_id:
        return {
            "success": False,
            "output": "",
            "duration": 0,
            "execution_trace": {},
            "error": (
                "SECURITY ERROR: workspace_id is REQUIRED for external agent execution. "
                "All agent sandboxes must be bound to a workspace."
            ),
        }

    # SECURITY: workspace_storage_base is REQUIRED
    workspace_storage_base = ctx.get("workspace_storage_base")
    if not workspace_storage_base:
        return {
            "success": False,
            "output": "",
            "duration": 0,
            "execution_trace": {},
            "error": (
                "SECURITY ERROR: workspace_storage_base is REQUIRED. "
                "Workspace must have storage_base_path configured."
            ),
        }

    # Get registry
    registry = get_agent_registry()

    # Get adapter
    adapter = registry.get_adapter(agent)
    if adapter is None:
        available = registry.list_agents()
        return {
            "success": False,
            "output": "",
            "duration": 0,
            "execution_trace": {},
            "error": f"Agent '{agent}' not found. Available: {available}",
        }

    # Get manifest for defaults
    manifest = registry.get_manifest(agent)

    # Check availability
    if not await adapter.is_available():
        return {
            "success": False,
            "output": "",
            "duration": 0,
            "execution_trace": {},
            "error": f"Agent '{agent}' is not installed or not accessible",
        }

    # Generate workspace-bound sandbox path
    execution_id = ctx.get("execution_id") or str(uuid.uuid4())
    sandbox_path = get_agent_sandbox(
        workspace_storage_base=workspace_storage_base,
        workspace_id=workspace_id,
        execution_id=execution_id,
        agent_id=agent,
    )

    # Use manifest defaults if not specified
    if allowed_tools is None and manifest:
        allowed_tools = manifest.defaults.get("allowed_skills", ["file", "web_search"])

    # Run preflight check with workspace context
    preflight_context = {
        "workspace_id": workspace_id,
        "workspace_storage_base": workspace_storage_base,
        "max_duration": max_duration,
        "project_id": ctx.get("project_id"),
    }

    preflight_result = await check_agent_preflight(
        task=task,
        allowed_skills=allowed_tools or ["file", "web_search"],
        sandbox_path=str(sandbox_path),
        context=preflight_context,
    )

    if not preflight_result.approved:
        return {
            "success": False,
            "output": "",
            "duration": 0,
            "execution_trace": {},
            "error": f"Preflight check failed: {'; '.join(preflight_result.blockers)}",
            "preflight": {
                "approved": False,
                "risk_level": preflight_result.risk_level,
                "blockers": preflight_result.blockers,
                "warnings": preflight_result.warnings,
            },
        }

    # Build request
    request = AgentRequest(
        task=task,
        sandbox_path=str(sandbox_path),
        allowed_tools=allowed_tools or ["file", "web_search"],
        denied_tools=denied_tools or [],
        max_duration_seconds=max_duration,
        project_id=ctx.get("project_id"),
        workspace_id=workspace_id,
        intent_id=ctx.get("intent_id"),
        lens_id=ctx.get("lens_id"),
    )

    # Execute
    logger.info(f"Executing {agent} task in workspace-bound sandbox: {sandbox_path}")
    response = await adapter.execute(request)

    # Collect trace for provenance
    collector = ExecutionTraceCollector(sandbox_path)
    trace = collector.collect_from_response(response, request, agent)
    await collector.save_trace(trace)

    # Return Playbook-compatible result
    return {
        "success": response.success,
        "output": response.output,
        "duration": response.duration_seconds,
        "execution_trace": {
            "execution_id": trace.execution_id,
            "agent": agent,
            "tool_calls": [tc.get("tool", "unknown") for tc in response.tool_calls],
            "files_created": response.files_created,
            "files_modified": response.files_modified,
            "sandbox_path": str(sandbox_path),
        },
        "error": response.error,
        "_provenance": {
            "trace_id": trace.execution_id,
            "task_hash": trace.task_hash,
            "intent_id": request.intent_id,
            "lens_id": request.lens_id,
            "workspace_id": workspace_id,
        },
    }


async def list_agents() -> Dict[str, Any]:
    """
    List all registered external agents.

    Returns:
        dict with agents list and their availability
    """
    from backend.app.services.external_agents import get_agent_registry

    registry = get_agent_registry()
    agents = registry.list_agents()
    manifests = registry.get_all_manifests()
    availability = await registry.check_availability()

    return {
        "agents": [
            {
                "name": name,
                "available": availability.get(name, False),
                "description": manifests[name].description if name in manifests else "",
                "risk_level": (
                    manifests[name].risk_level if name in manifests else "unknown"
                ),
            }
            for name in agents
        ]
    }


async def check_agent(agent: str) -> Dict[str, Any]:
    """
    Check if a specific agent is available.

    Args:
        agent: Agent name to check

    Returns:
        dict with available, version, manifest info
    """
    from backend.app.services.external_agents import get_agent_registry

    registry = get_agent_registry()
    adapter = registry.get_adapter(agent)
    manifest = registry.get_manifest(agent)

    if adapter is None:
        return {
            "available": False,
            "error": f"Agent '{agent}' not registered",
        }

    is_available = await adapter.is_available()

    return {
        "available": is_available,
        "version": adapter.get_version() if is_available else None,
        "manifest": (
            {
                "name": manifest.name if manifest else agent,
                "description": manifest.description if manifest else "",
                "risk_level": manifest.risk_level if manifest else "unknown",
                "requires_sandbox": manifest.requires_sandbox if manifest else True,
            }
            if manifest
            else None
        ),
    }


# Legacy alias for backward compatibility
async def moltbot_execute(
    task: str,
    allowed_skills: Optional[List[str]] = None,
    denied_tools: Optional[List[str]] = None,
    max_duration: int = 300,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a Moltbot task (legacy API).

    Use execute_agent(agent="moltbot", ...) for new code.
    """
    return await execute_agent(
        agent="moltbot",
        task=task,
        allowed_tools=allowed_skills,
        denied_tools=denied_tools,
        max_duration=max_duration,
        context=context,
    )


# Tool registry for Playbook integration
EXTERNAL_AGENT_TOOLS = {
    "execute": {
        "function": execute_agent,
        "description": "Execute a task using a registered external agent",
        "inputs": {
            "agent": {"type": "string", "required": True},
            "task": {"type": "string", "required": True},
            "allowed_tools": {"type": "array", "default": None},
            "denied_tools": {"type": "array", "default": []},
            "max_duration": {"type": "integer", "default": 300},
        },
        "governance": {
            "risk_level": "high",
            "requires_sandbox": True,
        },
    },
    "list": {
        "function": list_agents,
        "description": "List all registered external agents",
        "inputs": {},
        "governance": {"risk_level": "low"},
    },
    "check": {
        "function": check_agent,
        "description": "Check if a specific agent is available",
        "inputs": {"agent": {"type": "string", "required": True}},
        "governance": {"risk_level": "low"},
    },
    # Legacy
    "moltbot_execute": {
        "function": moltbot_execute,
        "description": "Execute a Moltbot task (legacy, use 'execute' instead)",
        "inputs": {
            "task": {"type": "string", "required": True},
            "allowed_skills": {"type": "array", "default": ["file", "web_search"]},
        },
        "governance": {"risk_level": "high", "requires_sandbox": True},
    },
}

"""Read-only host resource runtime adapter catalog."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_ADAPTERS: tuple[dict[str, Any], ...] = (
    {
        "adapter_id": "apple_mlx_vlm",
        "label": "Apple MLX VLM",
        "category": "local_model_runtime",
        "platforms": ["darwin"],
        "transports": ["mlx_vlm_http"],
        "worker_capable": True,
        "model_binding_policy": "required",
        "default_model_binding_scope": "local",
        "default_model_binding_profile": "vision",
        "default_capabilities": ["vision"],
        "permission_scopes": ["model.invoke", "host.local"],
        "endpoint_required": True,
        "worker_spawn_policy": "managed_by_host_bridge",
    },
    {
        "adapter_id": "windows_foundry_winml",
        "label": "Windows AI Foundry / WinML",
        "category": "local_model_runtime",
        "platforms": ["windows"],
        "transports": ["windows_foundry_local", "winml"],
        "worker_capable": True,
        "model_binding_policy": "required",
        "default_model_binding_scope": "local",
        "default_model_binding_profile": "vision",
        "default_capabilities": ["vision", "multimodal"],
        "permission_scopes": ["model.invoke", "host.local"],
        "endpoint_required": True,
        "worker_spawn_policy": "managed_by_host_bridge",
    },
    {
        "adapter_id": "ollama_llama_cpp",
        "label": "Ollama / llama.cpp",
        "category": "local_model_runtime",
        "platforms": ["darwin", "linux", "windows"],
        "transports": ["ollama_http", "llama_cpp_http"],
        "worker_capable": True,
        "model_binding_policy": "required",
        "default_model_binding_scope": "local",
        "default_model_binding_profile": "vision",
        "default_capabilities": ["vision", "chat"],
        "permission_scopes": ["model.invoke", "host.local"],
        "endpoint_required": True,
        "worker_spawn_policy": "managed_by_host_bridge",
    },
    {
        "adapter_id": "nvidia_vllm",
        "label": "NVIDIA vLLM",
        "category": "model_runtime",
        "platforms": ["linux", "windows"],
        "transports": ["vllm_http", "openai_compatible_http"],
        "worker_capable": True,
        "model_binding_policy": "required",
        "default_model_binding_scope": "local",
        "default_model_binding_profile": "vision",
        "default_capabilities": ["vision", "chat", "embeddings"],
        "permission_scopes": ["model.invoke", "host.cluster"],
        "endpoint_required": True,
        "worker_spawn_policy": "managed_by_host_bridge",
    },
    {
        "adapter_id": "langgraph_agent_harness",
        "label": "LangGraph Agent Harness",
        "category": "agent_harness",
        "platforms": ["darwin", "linux", "windows"],
        "transports": ["http", "stdio", "websocket"],
        "worker_capable": True,
        "model_binding_policy": "optional",
        "default_model_binding_scope": "local",
        "default_model_binding_profile": "chat",
        "default_capabilities": ["agent_run", "tool_calling"],
        "permission_scopes": ["agent.run", "tool.invoke"],
        "endpoint_required": True,
        "worker_spawn_policy": "managed_by_host_bridge",
    },
    {
        "adapter_id": "openai_agents_sdk_harness",
        "label": "OpenAI Agents SDK Harness",
        "category": "agent_harness",
        "platforms": ["darwin", "linux", "windows"],
        "transports": ["http", "stdio"],
        "worker_capable": True,
        "model_binding_policy": "optional",
        "default_model_binding_scope": "cloud",
        "default_model_binding_profile": "chat",
        "default_capabilities": ["agent_run", "tool_calling"],
        "permission_scopes": ["agent.run", "tool.invoke"],
        "endpoint_required": True,
        "worker_spawn_policy": "managed_by_host_bridge",
    },
    {
        "adapter_id": "microsoft_agent_framework_harness",
        "label": "Microsoft Agent Framework Harness",
        "category": "agent_harness",
        "platforms": ["windows", "linux", "darwin"],
        "transports": ["http", "stdio"],
        "worker_capable": True,
        "model_binding_policy": "optional",
        "default_model_binding_scope": "local",
        "default_model_binding_profile": "chat",
        "default_capabilities": ["agent_run", "tool_calling"],
        "permission_scopes": ["agent.run", "tool.invoke"],
        "endpoint_required": True,
        "worker_spawn_policy": "managed_by_host_bridge",
    },
    {
        "adapter_id": "mcp_desktop_control",
        "label": "MCP Desktop Control",
        "category": "tool_bridge",
        "platforms": ["darwin", "linux", "windows"],
        "transports": ["mcp_stdio", "mcp_http"],
        "worker_capable": False,
        "model_binding_policy": "forbidden",
        "default_model_binding_scope": None,
        "default_model_binding_profile": None,
        "default_capabilities": ["tool_calling", "desktop_control"],
        "permission_scopes": ["tool.invoke"],
        "endpoint_required": True,
        "worker_spawn_policy": "never",
    },
    {
        "adapter_id": "a2a_protocol_connector",
        "label": "Agent2Agent Protocol Connector",
        "category": "protocol_connector",
        "platforms": ["darwin", "linux", "windows"],
        "transports": ["a2a_http"],
        "worker_capable": False,
        "model_binding_policy": "forbidden",
        "default_model_binding_scope": None,
        "default_model_binding_profile": None,
        "default_capabilities": ["agent_discovery", "task_exchange"],
        "permission_scopes": ["protocol.exchange"],
        "endpoint_required": True,
        "worker_spawn_policy": "never",
    },
    {
        "adapter_id": "ag_ui_protocol_connector",
        "label": "AG-UI Protocol Connector",
        "category": "protocol_connector",
        "platforms": ["darwin", "linux", "windows"],
        "transports": ["ag_ui_sse", "ag_ui_websocket"],
        "worker_capable": False,
        "model_binding_policy": "forbidden",
        "default_model_binding_scope": None,
        "default_model_binding_profile": None,
        "default_capabilities": ["agent_ui_events"],
        "permission_scopes": ["protocol.exchange"],
        "endpoint_required": True,
        "worker_spawn_policy": "never",
    },
)

_ADAPTER_BY_ID = {adapter["adapter_id"]: adapter for adapter in _ADAPTERS}


def clean_adapter_id(value: Any) -> str:
    return str(value or "").strip()


def list_runtime_adapters() -> list[dict[str, Any]]:
    return [deepcopy(adapter) for adapter in _ADAPTERS]


def get_runtime_adapter(adapter_id: Any) -> dict[str, Any] | None:
    normalized = clean_adapter_id(adapter_id)
    adapter = _ADAPTER_BY_ID.get(normalized)
    return deepcopy(adapter) if adapter else None


def require_runtime_adapter(adapter_id: Any) -> dict[str, Any]:
    adapter = get_runtime_adapter(adapter_id)
    if not adapter:
        raise ValueError("runtime_adapter_unknown")
    return adapter

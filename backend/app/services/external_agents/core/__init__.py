"""
External Agents Core Framework

Provides the base classes and utilities for integrating external runtime
adapters within Mindscape's governance layer.
"""

from backend.app.services.external_agents.core.base_adapter import (
    BaseRuntimeAdapter,
    RuntimeExecRequest,
    RuntimeExecResponse,
    # Backward compat aliases
    BaseAgentAdapter,
    AgentRequest,
    AgentResponse,
)
from backend.app.services.external_agents.core.execution_trace import (
    ExecutionTrace,
    ExecutionTraceCollector,
    ToolCall,
    FileChange,
)
from backend.app.services.external_agents.core.registry import (
    RuntimeRegistry,
    RuntimeManifest,
    get_runtime_registry,
    # Backward compat aliases
    AgentRegistry,
    AgentManifest,
    get_agent_registry,
)
from backend.app.services.external_agents.core.policies import (
    SandboxPolicy,
    NetworkPolicy,
    ToolAcquisitionPolicy,
    SecretsPolicy,
    ModelPolicy,
    RetentionPolicy,
    DoerWorkspaceConfig,
    RetentionTier,
    RiskLevel,
)
from backend.app.services.external_agents.core.workspace_sandbox_resolver import (
    WorkspaceSandboxResolver,
    get_agent_sandbox,
    validate_agent_sandbox,
)

__all__ = [
    # Base adapter (new names)
    "BaseRuntimeAdapter",
    "RuntimeExecRequest",
    "RuntimeExecResponse",
    # Base adapter (backward compat aliases)
    "BaseAgentAdapter",
    "AgentRequest",
    "AgentResponse",
    # Execution trace
    "ExecutionTrace",
    "ExecutionTraceCollector",
    "ToolCall",
    "FileChange",
    # Registry (new names)
    "RuntimeRegistry",
    "RuntimeManifest",
    "get_runtime_registry",
    # Registry (backward compat aliases)
    "AgentRegistry",
    "AgentManifest",
    "get_agent_registry",
    # Policies
    "SandboxPolicy",
    "NetworkPolicy",
    "ToolAcquisitionPolicy",
    "SecretsPolicy",
    "ModelPolicy",
    "RetentionPolicy",
    "DoerWorkspaceConfig",
    "RetentionTier",
    "RiskLevel",
    # Workspace Sandbox (Security)
    "WorkspaceSandboxResolver",
    "get_agent_sandbox",
    "validate_agent_sandbox",
]

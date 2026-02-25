"""
External Agents Package

Provides a pluggable architecture for integrating external AI runtimes
within Mindscape's governance layer.

## Architecture

```
external_agents/
├── core/                      # Core framework
│   ├── base_adapter.py        # Abstract base class
│   ├── execution_trace.py     # Trace collection
│   └── registry.py            # Runtime discovery
│
└── agents/                    # Pluggable runtimes
    └── <runtime_id>/          # Each runtime as subdirectory
        ├── RUNTIME.md         # Manifest
        └── adapter.py         # Implementation
```

## Usage

```python
from backend.app.services.external_agents import get_runtime_registry

registry = get_runtime_registry()
runtime = registry.get_adapter("your_runtime_id")

if await runtime.is_available():
    response = await runtime.execute(request)
```
"""

# Core framework exports
from backend.app.services.external_agents.core import (
    # Base adapter (new names)
    BaseRuntimeAdapter,
    RuntimeExecRequest,
    RuntimeExecResponse,
    # Base adapter (backward compat aliases)
    BaseAgentAdapter,
    AgentRequest,
    AgentResponse,
    # Execution trace
    ExecutionTrace,
    ExecutionTraceCollector,
    ToolCall,
    FileChange,
    # Registry (new names)
    RuntimeRegistry,
    RuntimeManifest,
    get_runtime_registry,
    # Registry (backward compat aliases)
    AgentRegistry,
    AgentManifest,
    get_agent_registry,
    # Policies
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

__all__ = [
    # Core framework (new names)
    "BaseRuntimeAdapter",
    "RuntimeExecRequest",
    "RuntimeExecResponse",
    # Core framework (backward compat aliases)
    "BaseAgentAdapter",
    "AgentRequest",
    "AgentResponse",
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
]

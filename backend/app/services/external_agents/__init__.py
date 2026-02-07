"""
External Agents Package

Provides a pluggable architecture for integrating external AI agents
within Mindscape's governance layer.

## Architecture

```
external_agents/
├── core/                      # Core framework
│   ├── base_adapter.py        # Abstract base class
│   ├── execution_trace.py     # Trace collection
│   └── registry.py            # Agent discovery
│
└── agents/                    # Pluggable agents
    └── <agent_id>/            # Each agent as subdirectory
        ├── AGENT.md           # Manifest
        └── adapter.py         # Implementation
```

## Usage

```python
from backend.app.services.external_agents import get_agent_registry

registry = get_agent_registry()
agent = registry.get_adapter("your_agent_id")

if await agent.is_available():
    response = await agent.execute(request)
```
"""

# Core framework exports
from backend.app.services.external_agents.core import (
    # Base adapter
    BaseAgentAdapter,
    AgentRequest,
    AgentResponse,
    # Execution trace
    ExecutionTrace,
    ExecutionTraceCollector,
    ToolCall,
    FileChange,
    # Registry
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
    # Core framework
    "BaseAgentAdapter",
    "AgentRequest",
    "AgentResponse",
    "ExecutionTrace",
    "ExecutionTraceCollector",
    "ToolCall",
    "FileChange",
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

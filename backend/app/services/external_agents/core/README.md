# External Agents Core Framework

This directory contains the core framework for integrating external AI agents
within Mindscape's governance layer.

## Directory Structure

```text
external_agents/
├── core/                         # Core framework (not pluggable)
│   ├── base_adapter.py           # Abstract base class for adapters
│   ├── execution_trace.py        # Common trace collection
│   ├── registry.py               # Agent discovery and registration
│   ├── policies.py               # Governance policies (Sandbox, Model, etc.)
│   └── workspace_sandbox_resolver.py  # Workspace-bound sandbox enforcement
│
└── agents/                       # Pluggable agent directory
    └── openclaw/                  # Each agent as a subdirectory
        ├── AGENT.md              # Agent manifest
        └── adapter.py            # Implementation
```

## Security: Workspace-Bound Execution

> **CRITICAL**: All external agent execution is now workspace-bound.

- `workspace_id` is **REQUIRED** for all agent execution
- Sandbox paths are auto-generated within `<workspace>/agent_sandboxes/`
- Manual sandbox path specification is not allowed

```python
from backend.app.services.external_agents.core import get_agent_sandbox

sandbox = get_agent_sandbox(
    workspace_storage_base="/path/to/workspace",
    workspace_id="ws-123",
    execution_id="exec-456",
    agent_id="openclaw",
)
# Result: /path/to/workspace/agent_sandboxes/openclaw/exec-456/
```

## Adding a New Agent

1. Create a new directory under `agents/`
2. Add `AGENT.md` with metadata
3. Implement `adapter.py` extending `BaseAgentAdapter`
4. The agent will be auto-discovered on startup


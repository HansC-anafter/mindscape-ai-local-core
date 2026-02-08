# External Agents Architecture

> **Version**: 1.1 (Pluggable Architecture)
> **Last Updated**: 2026-01-31
> **Status**: Phase 1 Implementation

This document describes the pluggable architecture for integrating external AI agents within Mindscape's governance layer.

---

## 1. Overview

External agents are autonomous AI systems that can perform complex tasks independently. Mindscape integrates these agents as **controlled executors** using a pluggable adapter pattern.

### Design Principles

1. **Pluggable**: New agents added by dropping directories into `agents/`
2. **Auto-Discovery**: Registry scans and registers agents on startup
3. **Unified API**: All agents share common `execute()` interface
4. **Governance**: All executions traced and sandboxed

---

## 2. Directory Structure

```
backend/app/services/external_agents/
├── __init__.py                # Package exports
├── README.md                  # Quick start guide
│
├── core/                      # Core framework (not pluggable)
│   ├── __init__.py
│   ├── base_adapter.py        # BaseAgentAdapter abstract class
│   ├── execution_trace.py     # ExecutionTrace, ExecutionTraceCollector
│   └── registry.py            # AgentRegistry, AgentManifest
│
└── agents/                    # Pluggable agent directory
    ├── example_agent/         # Example agent adapter
    │   ├── AGENT.md           # Manifest with metadata
    │   ├── __init__.py
    │   └── adapter.py         # ExampleAgentAdapter implementation
    │
    ├── claude_code/           # Claude Code adapter
    │   └── ...
    │
    └── langgraph/             # LangGraph adapter
        └── ...
```

---

## 3. Core Components

### 3.1 BaseAgentAdapter

Abstract base class that all agent adapters must extend:

```python
class BaseAgentAdapter(ABC):
    AGENT_NAME: str = "base"
    AGENT_VERSION: str = "0.0.0"
    ALWAYS_DENIED_TOOLS: List[str] = ["system.run", "gateway", "docker"]

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the agent is installed."""
        pass

    @abstractmethod
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Execute a task using this agent."""
        pass
```

### 3.2 AgentRegistry

Auto-discovers and manages agent adapters:

```python
from backend.app.services.external_agents import get_agent_registry

registry = get_agent_registry()

# List all agents
agents = registry.list_agents()  # ['example_agent', 'claude_code']

# Get specific adapter
agent = registry.get_adapter("example_agent")

# Check availability
availability = await registry.check_availability()
# {'example_agent': True, 'claude_code': False}
```

### 3.3 AGENT.md Manifest

Each agent requires an `AGENT.md` with YAML frontmatter:

```yaml
---
name: example_agent
version: "1.0.0"
description: Example External Agent Adapter
cli_command: example-agent
min_version: "0.1.0"

defaults:
  allowed_skills: ["file", "web_search"]
  denied_tools: ["system.run", "gateway", "docker"]
  max_duration: 300

governance:
  risk_level: high
  requires_sandbox: true
---

# Documentation content...
```

---

## 4. Adding a New Agent

### Step 1: Create Directory

```bash
mkdir -p backend/app/services/external_agents/agents/autogpt
```

### Step 2: Create AGENT.md

```yaml
---
name: autogpt
version: "1.0.0"
description: AutoGPT Agent Adapter
cli_command: autogpt

governance:
  risk_level: high
  requires_sandbox: true
---

# AutoGPT Agent

Documentation...
```

### Step 3: Implement Adapter

```python
# adapter.py
from backend.app.services.external_agents.core import (
    BaseAgentAdapter, AgentRequest, AgentResponse
)

class AutoGPTAdapter(BaseAgentAdapter):
    AGENT_NAME = "autogpt"
    AGENT_VERSION = "1.0.0"

    async def is_available(self) -> bool:
        # Check if AutoGPT is installed
        pass

    async def execute(self, request: AgentRequest) -> AgentResponse:
        # Execute task using AutoGPT
        pass
```

### Step 4: Verify Registration

```python
registry = get_agent_registry()
assert "autogpt" in registry.list_agents()
```

---

## 5. Playbook Integration

### Generic Execute Tool

```yaml
steps:
  - id: execute_agent
    tool: external_agent.execute
    inputs:
      agent: example_agent   # Any registered agent
      task: "Build a landing page"
      allowed_tools: ["file", "web_search"]
      max_duration: 300
```

### List Available Agents

```yaml
steps:
  - id: list_agents
    tool: external_agent.list
```

---

## 6. Security Model

### Workspace-Bound Sandbox Enforcement

> **CRITICAL**: All external agent execution is now workspace-bound.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Workspace Storage Base                            │
│  <workspace_storage_base>/                                           │
│  └── agent_sandboxes/                                                │
│      └── <agent_id>/           # e.g., claude_code, langgraph        │
│          └── <execution_id>/   # UUID per execution                 │
│              └── ...           # All agent files isolated here      │
└─────────────────────────────────────────────────────────────────────┘
```

**Security Requirements:**

| Requirement | Enforcement | Error if Missing |
|-------------|-------------|------------------|
| `workspace_id` | **REQUIRED** | SECURITY ERROR: workspace_id is REQUIRED |
| `workspace_storage_base` | **REQUIRED** | SECURITY ERROR: workspace_storage_base is REQUIRED |
| Sandbox path | Auto-generated | N/A (never manually specified) |

### Defense Layers

| Layer | Protection | Implementation |
|-------|------------|----------------|
| **Workspace Binding** | Execution isolation | `WorkspaceSandboxResolver` |
| **Registry** | Valid manifests | `AgentManifest` parsing |
| **Preflight** | Pattern detection | `AgentPreflightChecker` |
| **Config** | Tool restrictions | `ALWAYS_DENIED_TOOLS` |
| **Sandbox Path Validation** | Boundary check | `validate_agent_sandbox()` |
| **Timeout** | Resource limits | `asyncio.wait_for()` |
| **Audit** | Full trace | `ExecutionTraceCollector` |

### WorkspaceSandboxResolver

```python
from backend.app.services.external_agents.core import (
    get_agent_sandbox,
    validate_agent_sandbox,
)

# Generate workspace-bound sandbox path
sandbox = get_agent_sandbox(
    workspace_storage_base="/path/to/workspace/storage",
    workspace_id="ws-123",
    execution_id="exec-456",
    agent_id="example_agent",
)
# Result: /path/to/workspace/storage/agent_sandboxes/example_agent/exec-456/

# Validate sandbox is within workspace
is_valid, error = validate_agent_sandbox(
    sandbox_path=str(sandbox),
    workspace_storage_base="/path/to/workspace/storage",
)
```

### Always-Denied Tools

These tools are blocked for **all** agents:

- `system.run` - Host-level shell
- `gateway` - Mindscape gateway
- `docker` - Container escape

---

## 7. Multi-Workspace Pattern

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Mindscape Workspace Group                        │
├─────────────────────────────────────────────────────────────────────┤
│  Workspace A (Planning)     Workspace B (Review)                    │
│  └─ Define Intent           └─ Quality check                        │
│  └─ Configure Lens          └─ Approve/reject                       │
│                                                                      │
│  ┌───────────────────────────────────────────────────────┐          │
│  │  Workspace C (Agent Executor)                          │          │
│  │  ┌─────────────────────────────────────────────────┐  │          │
│  │  │  External Agent (Sandboxed)                    │  │          │
│  │  │  - Executes tasks from A                        │  │          │
│  │  │  - Outputs reviewed by B                        │  │          │
│  │  └─────────────────────────────────────────────────┘  │          │
│  └───────────────────────────────────────────────────────┘          │
│                              ↓                                       │
│               Shared Asset Provenance                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Related Documents

- [Asset Provenance Architecture](./asset-provenance.md)
- [Governance Decision & Risk Control Layer](./governance-decision-risk-control-layer.md)


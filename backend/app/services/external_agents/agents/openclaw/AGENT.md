---
name: openclaw
version: "1.0.0"
description: OpenClaw Agent Adapter for deep execution tasks
cli_command: openclaw
min_version: "0.1.0"

dependencies:
  - openclaw>=0.1.0

defaults:
  allowed_skills:
    - file
    - web_search
  denied_tools:
    - system.run
    - gateway
    - docker
  max_duration: 300
  model: anthropic/claude-sonnet-4-20250514

governance:
  risk_level: high
  requires_sandbox: true
---

# OpenClaw Agent Adapter

OpenClaw is an autonomous AI agent designed for deep execution tasks.
This adapter integrates OpenClaw within Mindscape's governance layer.

## Features

- **Sandbox Execution**: All tasks run within isolated project sandboxes
- **Tool Restrictions**: Configurable allowlist/denylist for tools
- **Execution Tracing**: Full trace collection for Asset Provenance
- **Timeout Enforcement**: Automatic termination on timeout

## Installation

### Option 1: pip (when available)

```bash
pip install openclaw
```

### Option 2: Clone repository

```bash
git clone https://github.com/anthropics/openclaw ~/.openclaw
```

## Usage

This adapter is automatically discovered by Mindscape when placed in
`backend/app/services/external_agents/agents/openclaw/`.

### Via Playbook

```yaml
steps:
  - id: execute
    tool: external_agent.openclaw
    inputs:
      task: "Build a landing page"
      allowed_skills: ["file", "web_search"]
```

### Direct API

```python
from backend.app.services.external_agents import get_agent_registry

registry = get_agent_registry()
openclaw = registry.get_adapter("openclaw")

if await openclaw.is_available():
    response = await openclaw.execute(request)
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `allowed_skills` | `["file", "web_search"]` | Allowed OpenClaw skills |
| `denied_tools` | `["system.run", "gateway", "docker"]` | Denied tools |
| `max_duration` | `300` | Max execution time (seconds) |
| `model` | `claude-sonnet-4-20250514` | LLM model |

## Security

### Always-Denied Tools

These tools are **never** permitted for sandboxed execution:

- `system.run` - Host-level shell access
- `gateway` - Mindscape gateway manipulation
- `docker` - Container escape risk

### Sandbox Restrictions

- OpenClaw can only access files within the sandbox directory
- Network requests are logged but not blocked by default
- All tool calls are recorded in the execution trace

## Related

- [External Agents Architecture](file:///docs/core-architecture/external-agents.md)
- [Asset Provenance](file:///docs/core-architecture/asset-provenance.md)

---
name: antigravity
version: "1.0.0"
description: Antigravity IDE Agent — dispatches coding tasks to IDE via WebSocket or MCP
cli_command: null

dependencies: []

defaults:
  allowed_skills:
    - file
    - terminal
    - browser
    - web_search
  denied_tools:
    - system.run
    - gateway
    - docker
  max_duration: 600

governance:
  risk_level: medium
  requires_sandbox: true
---

# Antigravity Agent Adapter

Antigravity is an AI coding agent that runs inside the IDE (e.g. VS Code).
This adapter dispatches coding tasks to Antigravity through a transport-agnostic
Dispatch Contract, supporting WebSocket Push (primary) and REST Polling (fallback).

## Features

- **WebSocket Push**: Zero-latency task dispatch via persistent WS connection
- **REST Polling Fallback**: Pending queue for disconnected or offline clients
- **Transport-Agnostic**: Unified Dispatch Contract across all transport layers
- **Governance Integration**: Full execution trace for Asset Provenance
- **Multi-Client Support**: Directed dispatch via target_client_id

## Architecture

Unlike CLI-based agents (e.g. OpenClaw), Antigravity does not execute via
subprocess. Instead, tasks are dispatched over the network to an IDE instance
that has an active WebSocket connection to the Mindscape backend.

```
AntigravityAdapter.execute()
  → Build Dispatch Contract payload
  → Send via WebSocket (or queue for polling)
  → Wait for ack + result
  → Parse into AgentResponse
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `allowed_skills` | `["file", "terminal", "browser", "web_search"]` | Allowed agent tools |
| `denied_tools` | `["system.run", "gateway", "docker"]` | Denied tools |
| `max_duration` | `600` | Max execution time (seconds) |
| `strategy` | `ws` | Transport strategy: `ws`, `polling`, or `sampling` |

## Transport Strategies

| Strategy | Primary Use | Latency | Reliability |
|----------|------------|---------|-------------|
| `ws` | Default — WebSocket Push | Immediate | Requires active connection |
| `polling` | Fallback — REST Polling | 1-5 seconds | Works when WS is unavailable |
| `sampling` | Experimental — MCP Sampling | Sync | Depends on IDE MCP routing |

## Security

- All dispatch payloads include `workspace_id` and `execution_id`
- WebSocket connections require token + nonce authentication
- Task results must include `governance.output_hash` for receipt verification

## Related

- [MCP Gateway Architecture](file:///docs/core-architecture/mcp-gateway.md)
- [External Agents Architecture](file:///docs/core-architecture/external-agents.md)
- [Asset Provenance](file:///docs/core-architecture/asset-provenance.md)

---
name: Claude Code CLI
version: "1.0.0"
description: Claude Code CLI Agent — dispatches tasks to Anthropic Claude Code CLI via WebSocket bridge with polling fallback

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

# Claude Code CLI Adapter

Dispatches coding tasks to Anthropic Claude Code CLI via the shared host bridge contract.

## Architecture

Uses the shared `external_agents.bridge` flow with polling retained as fallback:
- WebSocket dispatch to the real host-connected Claude Code surface
- Cross-worker routing through the shared agent dispatch manager
- Polling/DB fallback when no WS surface is reachable

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_duration` | `600` | Max execution time (seconds) |

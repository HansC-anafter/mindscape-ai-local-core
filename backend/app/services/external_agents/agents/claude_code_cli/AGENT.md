---
name: Claude Code CLI
version: "1.0.0"
description: Claude Code CLI Agent — dispatches tasks to Anthropic Claude Code CLI via polling

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

Dispatches coding tasks to Anthropic Claude Code CLI via the shared REST Polling pipeline.

## Architecture

Inherits all dispatch lifecycle logic from `PollingAgentAdapter`:
- DB-primary persistence (TasksStore)
- In-memory Future for instant notification
- Timeout recovery via DB check

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_duration` | `600` | Max execution time (seconds) |

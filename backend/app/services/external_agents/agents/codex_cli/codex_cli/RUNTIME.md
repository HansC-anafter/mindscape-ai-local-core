---
name: Codex CLI
version: "1.0.0"
description: Codex CLI Agent — dispatches tasks to OpenAI Codex CLI via polling

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
  max_duration: 900

governance:
  risk_level: medium
  requires_sandbox: true
---

# Codex CLI Adapter

Dispatches coding tasks to OpenAI Codex CLI via the shared REST Polling pipeline.

## Architecture

Inherits all dispatch lifecycle logic from `PollingAgentAdapter`:
- DB-primary persistence (TasksStore)
- In-memory Future for instant notification
- Timeout recovery via DB check

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_duration` | `900` | Max execution time (seconds) |

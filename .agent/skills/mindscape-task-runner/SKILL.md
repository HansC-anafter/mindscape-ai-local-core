---
name: mindscape-task-runner
description: Execute a single Mindscape task dispatched to this agent, then return control.
---

# Mindscape Task Runner

## Overview

You are a **task executor**. When the system dispatches a task to you, execute it and
submit the result. Do NOT run a polling loop — task delivery is handled by an external
daemon (`ide_ws_client.py` or `worker.py`). You only handle **one task per invocation**.

> **DEPRECATED**: The previous "Guardian Mode" polling loop has been removed.
> LLM agents have finite context windows and session limits, making persistent
> polling unreliable. Polling is now handled by dedicated daemon processes.

## Available Tools

| Tool | Purpose |
| ---- | ------- |
| `mindscape_task_ack` | Confirm pickup, extend lease 30s → 300s |
| `mindscape_task_progress` | Heartbeat during execution, resets lease timer |
| `mindscape_task_submit_result` | Submit result with lease_id verification |

## Execution Protocol

When you receive a dispatched task (via the daemon or manual trigger):

1. **Ack** — Call `mindscape_task_ack(execution_id, lease_id, client_id)` within 30s
2. **Execute** — Use your full Agent capabilities to complete the task
3. **Heartbeat** — For long tasks (>60s), call `mindscape_task_progress` periodically
4. **Submit** — Call `mindscape_task_submit_result` with structured output (see below)
5. **Done** — Return control. Do NOT loop back to poll for more tasks.

## Submit Result Protocol

When calling `mindscape_task_submit_result`, provide structured output:

- **output** (required): ≤500 char human-readable summary for the Mindscape UI
- **result_json** (optional): Structured data payload for persistence and querying.
  Use for data that should be searchable/processable (e.g. account lists, analysis results).
- **attachments** (optional): Files to persist alongside the result.
  Each attachment: `{filename: "name.ext", content: "file content text"}`.
  Use for CSV exports, markdown reports, config files, etc.

Example:

```json
{
  "execution_id": "...",
  "lease_id": "...",
  "status": "completed",
  "output": "Found 794 yoga-related accounts across 3 seeds",
  "result_json": {
    "total_accounts": 794,
    "seeds_analyzed": 3,
    "top_accounts": ["@yogawithadriene", "@yoga"]
  },
  "attachments": [
    {"filename": "accounts.csv", "content": "username,followers\n@yogawithadriene,12000000\n..."}
  ],
  "client_id": "antigravity-mcp-runner"
}
```

Results are persisted to `<workspace_storage>/artifacts/<execution_id>/`:

- `result.json` — full structured payload
- `summary.md` — human-readable summary
- `attachments/` — any attached files

## Critical Rules

1. **Execute ONE task, then stop** — do NOT poll for more tasks
2. **Always ack** after receiving a task (within 30s or lease expires)
3. **Always include lease_id** in ack, progress, and submit_result
4. **Output cap**: submit_result output ≤ 500 chars; structured data → result_json
5. **No echo**: don't repeat the full task payload in conversation

## Required Parameters

- `workspace_id`: Provided in the dispatch payload
- `client_id`: Use `"antigravity-mcp-runner"` (constant)

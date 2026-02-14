---
name: mindscape-task-runner
description: Pull and execute Mindscape tasks via MCP, reporting results back to the dispatch queue.
---

# Mindscape Task Runner (Guardian Mode)

## Overview

You are a **task runner agent**. You pull tasks from Mindscape, execute them, and submit results. The loop is autonomous — you never ask the user for permission to continue.

## Available Tools

| Tool | Purpose |
| ---- | ------- |
| `mindscape_task_next` | Short-poll (≤5s) for next task. Returns `{task, lease_id}` |
| `mindscape_task_ack` | Confirm pickup, extend lease 30s → 300s |
| `mindscape_task_progress` | Heartbeat during execution, resets lease timer |
| `mindscape_task_submit_result` | Submit result with lease_id verification |
| `mindscape_task_list_inflight` | Resume after crash — lists your unfinished tasks |

## Guardian Protocol

```
STARTUP:
  1. Call mindscape_task_list_inflight(client_id)
     → If inflight tasks exist: resume them (submit or re-execute)

LOOP:
  1. Call mindscape_task_next(workspace_id, client_id, wait_seconds=5)
     → Blocks up to 5s. Do NOT sleep or poll manually.

  2. IF task returned:
     a. Call mindscape_task_ack(execution_id, lease_id, client_id)
        → Confirms pickup, extends lease to 300s
     b. Execute the task using your full Agent capabilities
     c. For long tasks: call mindscape_task_progress(execution_id, lease_id)
        every 60s to prevent lease expiry
     d. Call mindscape_task_submit_result with structured output (see below)
     e. GOTO LOOP step 1

  3. IF empty (timeout):
     a. GOTO LOOP step 1. Do NOT ask the user.
```

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

1. **NEVER stop the loop** unless user says "stop" or "exit"
2. **NEVER ask user** for permission to continue polling
3. **Always ack** after receiving a task (within 30s or lease expires)
4. **Always include lease_id** in ack, progress, and submit_result
5. **Output cap**: submit_result output ≤ 500 chars; structured data → result_json
6. **No echo**: don't repeat the full task payload in conversation
7. **Backoff**: if 3 consecutive empty polls, increase to wait_seconds=5 (already default)

## Required Parameters

- `workspace_id`: Get from workspace context or ask user once at startup
- `client_id`: Use `"antigravity-mcp-runner"` (constant)

# Codex CLI E2E Trace Runbook

## Backup First

This E2E writes `meeting session`, `task`, `artifact`, and `canonical memory` data.
Take a database backup before running it.

```bash
docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_test_$(date +%Y%m%d_%H%M%S).sql
```

## Scope

This runbook records two end-to-end paths:

1. `Closure E2E`: `meeting -> dispatch -> execution completion -> artifact landing -> canonical memory evidence`
2. `Readback E2E`: `second meeting -> selected memory packet -> prior canonical memory served back`

Use this when validating the meeting-to-execution closure for shared CLI surfaces.

## Critical Preconditions

- Do **not** create a fresh isolated workspace for this run.
- Use an existing workspace that already shows an authenticated `codex_cli` bridge in `GET /api/v1/mcp/agent/status`.
- If any debug or manual polling step hits `/api/v1/mcp/agent/pending`, always pass `surface=codex_cli`. Do not rely on a route default.

Provider check:

```bash
curl -sS http://localhost:8200/api/v1/mcp/agent/status
```

Pass:

- target workspace is present under `workspaces`
- at least one client shows `"surface_type": "codex_cli"`
- the client is authenticated

Fail:

- workspace is absent from status
- only `gemini_cli` or other surfaces are connected
- no authenticated `codex_cli` client exists

## Trace Artifact Layout

Create one trace directory per run:

```text
data/e2e-traces/<run_id>/
  closure/
  readback/
```

Every checkpoint stores three artifacts:

- `NN_<slug>.png`: screenshot
- `NN_<slug>.json`: raw request/response payload
- `NN_<slug>.md`: 2-4 sentence note explaining what the screenshot proves

Recommended screenshot style:

- capture the full response body and the request URL
- if using browser devtools, include response headers only when relevant
- for before/after comparisons, use a single side-by-side image when possible

## Problem Targets

1. `P1 Provider mismatch`: E2E fails because the chosen workspace has no live `codex_cli` bridge.
2. `P2 Wrong ingress`: using `meeting_sessions/start/end` only tests session persistence, not dispatch/finalize/writeback.
3. `P3 Closure gap`: execution lands an artifact, but canonical memory detail does not reflect execution evidence or artifact evidence.
4. `P4 Readback gap`: second meeting does not receive the prior canonical memory item through the selected memory packet.

## Closure E2E

This path must use `POST /api/handoff-bundles/compile`, not `meeting_sessions/start/end`.

### 00 Provider Status

- Files:
  - `closure/00_provider_status.png`
  - `closure/00_provider_status.json`
  - `closure/00_provider_status.md`
- Command:

```bash
curl -sS http://localhost:8200/api/v1/mcp/agent/status
```

- What to explain:
  - this run uses an existing workspace with authenticated `codex_cli`
  - this avoids false negatives caused by spinning up a workspace without a provider
- Pass:
  - target workspace appears in status with authenticated `codex_cli`
- Fail:
  - no matching workspace or no authenticated `codex_cli`

### 01 Compile Request

- Files:
  - `closure/01_compile_request.png`
  - `closure/01_compile_request.json`
  - `closure/01_compile_request.md`
- Request shape:
  - `workspace_id`
  - `project_id`
  - `thread_id`
  - `profile_id`
  - a small deliverable request, for example `Produce partner_brief.md summarizing this partnership direction`
- What to explain:
  - this is the full meeting ingress
  - the request is intentionally small so the run validates closure mechanics, not model creativity
- Pass:
  - request is sent to `/api/handoff-bundles/compile`
- Fail:
  - request goes through `meeting_sessions/start` or another partial ingress

### 02 Compile Response

- Files:
  - `closure/02_compile_response.png`
  - `closure/02_compile_response.json`
  - `closure/02_compile_response.md`
- Capture:
  - response body from `POST /api/handoff-bundles/compile`
- What to explain:
  - prove that compile completed and returned `session_id`
  - record any `task_ir_id` or related dispatch metadata
- Pass:
  - response includes `session_id`
  - compile status is successful
- Fail:
  - no `session_id`
  - compile request does not finish successfully

### 03 Closed Session Snapshot

- Files:
  - `closure/03_session_after_close.png`
  - `closure/03_session_after_close.json`
  - `closure/03_session_after_close.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/meeting-sessions/<session_id>"
```

- What to explain:
  - prove the meeting closed cleanly
  - prove close-time stitching and writeback metadata are present
- Pass:
  - `status == "closed"`
  - `action_items[0].execution_id` exists
  - `metadata.canonical_memory_item_id` exists
  - `metadata.memory_impact_trace` exists
- Fail:
  - session remains open
  - `execution_id` is missing from action items
  - canonical memory metadata is missing

### 04 Session Events

- Files:
  - `closure/04_session_events.png`
  - `closure/04_session_events.json`
  - `closure/04_session_events.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/meeting-sessions/<session_id>/events"
```

- What to explain:
  - show the event stream for the session
  - capture whether meeting end and memory writeback events are visible
- Pass:
  - `MEETING_END` exists
  - `MEMORY_WRITEBACK` is present if emitted in the session stream
- Fail:
  - event stream does not show the session closing path

### 05 Synthetic Completion Request

- Files:
  - `closure/05_completion_request.png`
  - `closure/05_completion_request.json`
  - `closure/05_completion_request.md`
- Submit completion through the stable completion ingress.
- Payload should include:
  - `execution_id`
  - `output`
  - `result_json.progress`
  - `result_json.metadata`
  - `attachments` with at least one named artifact such as `partner_brief.md`
- What to explain:
  - this payload is designed to exercise artifact landing and progress extraction
- Pass:
  - request is accepted
- Fail:
  - completion ingress rejects the payload

### 06 Landed Result

- Files:
  - `closure/06_landed_result.png`
  - `closure/06_landed_result.json`
  - `closure/06_landed_result.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/mcp/agent/result/<execution_id>"
```

- What to explain:
  - show that the execution result has been landed into storage and indexed
- Pass:
  - `status == "completed"`
  - `storage_ref` or `artifact_id` exists
  - attachment index contains `partner_brief.md`
- Fail:
  - landed result is missing
  - no storage or artifact reference is returned

### 07 Progress Snapshot

- Files:
  - `closure/07_progress_snapshot.png`
  - `closure/07_progress_snapshot.json`
  - `closure/07_progress_snapshot.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/executions/<execution_id>/progress-snapshot"
```

- What to explain:
  - confirm that artifact content can be surfaced back as execution progress
- Pass:
  - `progress.percent == 100`
  - `artifact_id` exists
- Fail:
  - progress snapshot is absent
  - landed artifact cannot be correlated back to execution status

### 08 Memory List

- Files:
  - `closure/08_memory_list.png`
  - `closure/08_memory_list.json`
  - `closure/08_memory_list.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/governance/memory"
```

- What to explain:
  - show that the workspace now has a canonical memory item from this run
- Pass:
  - list contains the canonical memory item for the session
- Fail:
  - canonical memory item is absent

### 09 Memory Detail Before/After

- Files:
  - `closure/09_memory_detail_before_after.png`
  - `closure/09_memory_detail_before_after.json`
  - `closure/09_memory_detail_before_after.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/governance/memory/<memory_item_id>"
```

- What to explain:
  - this is the closure proof point
  - compare memory evidence immediately after session close and again after execution completion
- Pass:
  - evidence contains `task_execution`
  - ideal state after completion also contains `artifact_result`
- Fail:
  - no execution evidence exists
  - artifact landed successfully but memory detail never reflects artifact evidence

### 10 Memory Impact Graph

- Files:
  - `closure/10_memory_impact_graph.png`
  - `closure/10_memory_impact_graph.json`
  - `closure/10_memory_impact_graph.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/governance/memory-impact-graph?session_id=<session_id>"
```

- What to explain:
  - show that the graph focus points back to this session and execution lineage
- Pass:
  - `focus.execution_ids` includes the run execution
  - graph contains session and memory nodes
- Fail:
  - graph focus is missing execution lineage

## Readback E2E

Only run this after `Closure E2E` passes through Node 09 at least at the `task_execution` level.

### 00 Provider Status

- Files:
  - `readback/00_provider_status.png`
  - `readback/00_provider_status.json`
  - `readback/00_provider_status.md`
- Re-run the same provider status check to prove the workspace still has live `codex_cli`.

### 01 Follow-up Compile Request

- Files:
  - `readback/01_followup_compile_request.png`
  - `readback/01_followup_compile_request.json`
  - `readback/01_followup_compile_request.md`
- What to explain:
  - this is the second meeting in the same workspace
  - the prompt should be a follow-up that can benefit from prior memory

### 02 Follow-up Compile Response

- Files:
  - `readback/02_followup_compile_response.png`
  - `readback/02_followup_compile_response.json`
  - `readback/02_followup_compile_response.md`
- Pass:
  - second `session_id` exists

### 03 Follow-up Session Metadata

- Files:
  - `readback/03_followup_session_selected_packet.png`
  - `readback/03_followup_session_selected_packet.json`
  - `readback/03_followup_session_selected_packet.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/meeting-sessions/<second_session_id>"
```

- What to explain:
  - show `metadata.selected_memory_packet`
  - show `metadata.selected_memory_packet_node_ids`
- Pass:
  - selected packet metadata exists
- Fail:
  - no selected memory packet was attached

### 04 Packet-to-Memory Match

- Files:
  - `readback/04_followup_selected_packet_match.png`
  - `readback/04_followup_selected_packet_match.json`
  - `readback/04_followup_selected_packet_match.md`
- What to explain:
  - prove the first run's canonical memory item is actually inside the second run's selected packet
- Pass:
  - `selected_memory_packet_node_ids` contains `memory_item:<first_memory_item_id>`
- Fail:
  - second run selected a packet, but not the prior canonical memory item

### 05 Follow-up Memory Impact Graph

- Files:
  - `readback/05_followup_memory_impact_graph.png`
  - `readback/05_followup_memory_impact_graph.json`
  - `readback/05_followup_memory_impact_graph.md`
- Command:

```bash
curl -sS "http://localhost:8200/api/v1/workspaces/<workspace_id>/governance/memory-impact-graph?session_id=<second_session_id>"
```

- What to explain:
  - show that the second session, selected packet, and prior memory item share a visible lineage in the graph
- Pass:
  - graph nodes and edges are non-empty
  - graph focus points to the second session
- Fail:
  - no graph linkage back to selected memory or prior canonical item

## Red-Light Checks

Stop the run and file a defect immediately if either of these happens:

- Node 03 has no `action_items[].execution_id`
- Node 09 shows landed artifacts but canonical memory detail never reflects execution evidence

## Final Trace Bundle

At the end of the run, add a short summary file:

```text
data/e2e-traces/<run_id>/summary.md
```

It should contain:

- workspace ID
- first and second session IDs
- execution ID
- first canonical memory item ID
- pass/fail result for each node
- open defects, if any

---
name: browser-runner-resource-triage-plan
description: Evidence-based implementation plan for reducing browser-runner resource amplification without changing task semantics, queue contents, or lock behavior.
---

# Browser Runner Resource Triage Plan

## Core Rule

Only remove proven resource waste. Do not change task semantics, do not mutate pending work, and do not weaken lock-based concurrency.

## Constraints

- `pending` tasks are queue state, not live resource usage.
- A profile may run multiple tasks when their resolved locks differ.
- Two running tasks sharing the same effective lock is a bug; legal parallelism under distinct locks is not.
- Do not change reference selection, pin/analyze behavior, or source-mode semantics.
- Do not cancel, delete, reorder, or "clean up" queued work.

## Proven Findings

1. `runner-browser` can hit `OOMKilled=true` while still staying `running`, which leaves the user-facing execution looking alive while child work is repeatedly killed.
2. Browser-runner memory spikes are driven by active child/bootstrap and browser-launch amplification, not by `pending` rows.
3. Multiple `ig_batch_pin_references` tasks were running legally under different profiles / locks.
4. The current resource amplifiers are:
   - heavyweight runner child bootstrap
   - per-task fan-out into `ig_pin_reference`
   - per-item browser fallback launches from thumbnail fetch failure paths
5. The intended remediation surface is resource control only, not workflow logic changes.

## Problem Register

1. **Total active browser-task ceiling is too loose**: the browser runner allows enough simultaneous active work to recreate memory/PID blow-ups under valid cross-lock parallelism.
2. **Browser fallback launch path is insufficiently bounded**: when thumbnail fetches fail, repeated browser launches can amplify process count far beyond the number of active tasks.
3. **Resource safeguards are implicit, not explicit**: the repo does not state a clean operator-facing boundary between lock concurrency and total browser-runner capacity.

## Implementation Plan

### 1. Add a total browser-runner task cap

Resolves Problem #1.

- Keep existing lock semantics unchanged.
- Keep cross-profile / cross-lock parallelism allowed.
- Limit only the total number of active tasks in `runner-browser`.
- Implement as configuration, not playbook logic.

Target:

- `backend/app/runner/*`: no lock changes
- `docker-compose.yml`: set browser-runner default `LOCAL_CORE_RUNNER_BROWSER_MAX_INFLIGHT` to a safer ceiling while preserving env override

Acceptance:

- The browser runner still accepts multiple tasks when locks differ.
- Total browser-runner task concurrency is bounded by config.

### 2. Add a global browser-fallback launch cap

Resolves Problem #2.

- Do not change when fallback is logically allowed.
- Do not change what the task is trying to fetch.
- Only bound how many browser fallback launches may run at the same time inside one runner process.
- Implement as an environment-controlled semaphore around the browser fallback launch path.

Target:

- `backend/app/capabilities/ig/services/thumbnail_fetcher.py`

Acceptance:

- Browser fallback still works.
- Concurrent fallback launches are capped globally.
- Fallback pressure scales with the configured cap, not with the number of failing shortcodes.

### 3. Keep lock behavior and queue state untouched

Resolves Problem #3.

- Do not change concurrency-key resolution.
- Do not change same-lock serialization.
- Do not change pending-task storage or reordering.
- Do not change task routing or playbook semantics.

Acceptance:

- Effective-lock behavior before/after remains equivalent.
- Queue contents are unchanged by this remediation.

## Explicit Non-Goals

- No queue cleanup
- No pending-task cancellation
- No source-mode rewrite
- No change to which references are pinned or analyzed
- No change to lock semantics
- No change to same-profile distinct-lock parallelism

## Validation SOP

### Runtime validation

1. Restart `runner-browser`.
2. Confirm the container comes up normally.
3. Confirm multiple running tasks can still coexist when their locks differ.
4. Confirm same-lock tasks do not run concurrently.
5. Observe memory/PID growth during active thumbnail-fetch pressure.

Pass:

- `runner-browser` stays below the memory cliff that previously triggered immediate OOM.
- PID count grows in a bounded way.
- Legal cross-lock concurrency still works.
- No queue mutation occurred.

Fail:

- Container immediately returns to OOM / extreme PID growth.
- Lock behavior changes.
- Pending work is mutated.

### Commands

```bash
docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}' mindscape-ai-local-core-runner-browser

docker inspect --format '{{json .State}}' mindscape-ai-local-core-runner-browser

docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c \
"SELECT id, status, execution_context->'inputs'->>'user_data_dir' AS user_data_dir, created_at
 FROM tasks
 WHERE pack_id='ig_batch_pin_references' AND status='running'
 ORDER BY created_at;"

docker exec mindscape-ai-local-core-runner-browser sh -lc \
"ps -eo pid,ppid,%cpu,%mem,rss,cmd | grep -E 'spawn_main|playwright/driver/node|/usr/lib/chromium/chromium' | grep -v grep | head -120"
```

## Deliverable Shape

The finished remediation should leave:

- legal lock-based concurrency intact
- total browser-runner task concurrency explicitly bounded
- browser fallback launch count explicitly bounded
- no changes to task semantics
- no queue mutation

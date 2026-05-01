# IG Docker Runtime Audit — 2026-04-22

Scope: audit every visible Docker container on the host, then isolate the current IG symptom: queued seeds visible in UI while the sidebar shows no or too few active runs.

Method: only claims backed by runtime evidence are marked as facts. Code-path analysis is separated and labeled as inference.

Note: source-side stack identifiers below are scrubbed to generic placeholders.

## 1. Container Inventory Snapshot

Evidence 1.1 — `docker ps -a`

Command:

```bash
docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.RunningFor}}'
```

Output:

```text
mindscape-ai-local-core-frontend|mindscape-ai-local-core-frontend|Up 36 seconds (health: starting)|2 days ago
mindscape-ai-local-core-backend|mindscape-ai-local-core-backend|Up 28 seconds (health: starting)|2 days ago
mindscape-ai-local-core-backend-control|mindscape-ai-local-core-backend|Up 35 seconds (health: starting)|2 days ago
mindscape-ai-local-core-runner-browser|mindscape-ai-local-core-runner|Up 17 minutes|2 days ago
mindscape-ai-local-core-runner-vision|mindscape-ai-local-core-runner|Up 39 hours|7 days ago
mindscape-ai-local-core-runner-default|mindscape-ai-local-core-runner|Up 3 days|7 days ago
mindscape-ai-local-core-xtts|mindscape-ai-local-core-xtts-service|Up 3 days (healthy)|3 weeks ago
mindscape-ai-local-core-postgres|pgvector/pgvector:pg16|Up 3 days (healthy)|3 weeks ago
mindscape-ai-local-core-redis|redis:7-alpine|Up 3 days (healthy)|3 weeks ago
mindscape-ai-local-core-media-proxy|mindscape-ai-local-core-media-proxy|Up 3 days (healthy)|3 weeks ago
mindscape-ai-local-core-whisper|mindscape-ai-local-core-whisper-service|Up 3 days (healthy)|3 weeks ago
source-stack-api-1|source-stack-api|Up 3 days (healthy)|3 weeks ago
mindscape-ai-gpu-executor-backend|mindscape-ai-local-core-gpu-executor-backend|Created|3 weeks ago
mindscape-ai-gpu-executor-redis|redis:7-alpine|Up 3 days (healthy)|3 weeks ago
mindscape-ai-gpu-executor-postgres|pgvector/pgvector:pg16|Up 3 days (healthy)|3 weeks ago
site-hub-gsm-agent-1|alpine:3.20|Exited (137) 3 weeks ago|3 weeks ago
site-hub-site-hub-registry-api-1|site-hub-site-hub-registry-api|Exited (137) 3 weeks ago|3 weeks ago
site-hub-site-hub-redis-1|redis:7-alpine|Exited (255) 3 weeks ago|3 weeks ago
site-hub-registry-db-1|postgis/postgis:15-3.4|Exited (255) 3 weeks ago|3 weeks ago
mindscape-ai-local-core-ocr|mindscape-ai-local-core-ocr-service|Exited (0) 4 weeks ago|4 weeks ago
source-stack-redis-1|redis:7-alpine|Up 3 days (healthy)|3 months ago
source-stack-postgres-1|postgres:15-alpine|Up 3 days (healthy)|3 months ago
```

Evidence 1.2 — `docker inspect`

Command:

```bash
docker inspect -f '{{.Name}}|{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}|{{.State.StartedAt}}|{{.State.FinishedAt}}|{{.State.ExitCode}}|{{.State.Error}}' ...
```

Output:

```text
/mindscape-ai-local-core-frontend|mindscape-ai-local-core-frontend|running|healthy|0|2026-04-21T20:48:45.515631305Z|2026-04-21T20:48:45.04958718Z|0|
/mindscape-ai-local-core-backend|mindscape-ai-local-core-backend|running|starting|0|2026-04-21T20:48:53.470573836Z|2026-04-21T20:48:51.629753919Z|0|
/mindscape-ai-local-core-backend-control|mindscape-ai-local-core-backend|running|healthy|0|2026-04-21T20:48:46.473705333Z|2026-04-21T20:48:46.070034847Z|0|
/mindscape-ai-local-core-runner-browser|mindscape-ai-local-core-runner|running|none|1|2026-04-21T20:31:57.559148047Z|2026-04-21T20:31:57.526176256Z|0|
/mindscape-ai-local-core-runner-vision|mindscape-ai-local-core-runner|running|none|0|2026-04-20T05:57:05.633529256Z|2026-04-20T05:57:05.251526839Z|0|
/mindscape-ai-local-core-runner-default|mindscape-ai-local-core-runner|running|none|0|2026-04-18T12:32:56.793080001Z|2026-04-18T12:32:54.271854542Z|0|
/mindscape-ai-local-core-xtts|mindscape-ai-local-core-xtts-service|running|healthy|0|2026-04-18T12:32:56.808062335Z|2026-04-18T12:32:54.2715565Z|0|
/mindscape-ai-local-core-postgres|pgvector/pgvector:pg16|running|healthy|0|2026-04-18T12:32:56.80534571Z|2026-04-18T12:32:54.271041875Z|0|
/mindscape-ai-local-core-redis|redis:7-alpine|running|healthy|0|2026-04-18T12:32:56.801749835Z|2026-04-18T12:32:54.2717195Z|0|
/mindscape-ai-local-core-media-proxy|mindscape-ai-local-core-media-proxy|running|healthy|0|2026-04-18T12:32:56.811743751Z|2026-04-18T12:32:54.272257167Z|0|
/mindscape-ai-local-core-whisper|mindscape-ai-local-core-whisper-service|running|healthy|0|2026-04-18T12:32:56.794109168Z|2026-04-18T12:32:54.271780125Z|0|
/source-stack-api-1|source-stack-api|running|healthy|0|2026-04-18T12:32:56.814668793Z|2026-04-18T12:32:54.271620333Z|0|
/mindscape-ai-gpu-executor-backend|mindscape-ai-local-core-gpu-executor-backend|created|none|0|0001-01-01T00:00:00Z|0001-01-01T00:00:00Z|0|
/mindscape-ai-gpu-executor-redis|redis:7-alpine|running|healthy|0|2026-04-18T12:32:56.81062171Z|2026-04-18T12:32:54.271806583Z|0|
/mindscape-ai-gpu-executor-postgres|pgvector/pgvector:pg16|running|healthy|0|2026-04-18T12:32:56.802549168Z|2026-04-18T12:32:54.271816208Z|0|
/site-hub-gsm-agent-1|alpine:3.20|exited|unhealthy|0|2026-03-26T11:21:45.460040835Z|2026-03-26T11:31:34.215961177Z|137|
/site-hub-site-hub-registry-api-1|site-hub-site-hub-registry-api|exited|unhealthy|1|2026-03-26T11:21:59.424183508Z|2026-03-26T11:31:23.901306089Z|137|
/site-hub-site-hub-redis-1|redis:7-alpine|exited|none|0|2026-03-26T05:38:57.437412051Z|2026-03-26T11:21:42.647191834Z|255|
/site-hub-registry-db-1|postgis/postgis:15-3.4|exited|starting|0|2026-03-26T05:38:57.415265134Z|2026-03-26T11:21:42.6470515Z|255|
/mindscape-ai-local-core-ocr|mindscape-ai-local-core-ocr-service|exited|unhealthy|0|2026-03-23T20:07:00.750119253Z|2026-03-23T20:07:11.58918655Z|0|
/source-stack-redis-1|redis:7-alpine|running|healthy|0|2026-04-18T12:32:56.801669376Z|2026-04-18T12:32:54.271839417Z|0|
/source-stack-postgres-1|postgres:15-alpine|running|healthy|0|2026-04-18T12:32:56.813124335Z|2026-04-18T12:32:54.272822375Z|0|
```

Facts from 1.1 + 1.2:

- `mindscape-ai-local-core-frontend`, `mindscape-ai-local-core-backend`, and `mindscape-ai-local-core-backend-control` all restarted around `2026-04-21T20:48Z`.
- `mindscape-ai-local-core-runner-browser` has `RestartCount=1`.
- `mindscape-ai-local-core-ocr` is not running.
- `mindscape-ai-gpu-executor-backend` is only `created`, not running.
- Four `site-hub-*` containers are exited and stale.

Evidence 1.3 — `docker stats --no-stream`

Command:

```bash
docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}|{{.PIDs}}'
```

Output:

```text
mindscape-ai-local-core-frontend|141.79%|1.04GiB / 15.6GiB|25.7kB / 10.6kB|63.3MB / 15.2MB|48
mindscape-ai-local-core-backend|82.48%|410.4MiB / 6GiB|170kB / 122kB|1.14MB / 0B|1
mindscape-ai-local-core-backend-control|102.15%|481.1MiB / 6GiB|256kB / 202kB|1.65MB / 0B|4
mindscape-ai-local-core-runner-browser|145.84%|3.568GiB / 6GiB|7.51GB / 25.1MB|1.96GB / 2.2GB|65
mindscape-ai-local-core-runner-vision|65.04%|2.717GiB / 6GiB|14.7GB / 7.29GB|2.56GB / 54.7MB|54
mindscape-ai-local-core-runner-default|2.99%|148.6MiB / 6GiB|233MB / 300MB|872MB / 316MB|21
mindscape-ai-local-core-xtts|0.51%|61.61MiB / 15.6GiB|104kB / 126B|2.93GB / 106MB|18
mindscape-ai-local-core-postgres|93.39%|371.4MiB / 15.6GiB|94.5GB / 405GB|16GB / 57.4MB|37
mindscape-ai-local-core-redis|1.02%|8.277MiB / 15.6GiB|291MB / 182MB|1.3GB / 3.69MB|6
mindscape-ai-local-core-media-proxy|0.18%|85.16MiB / 15.6GiB|23.7MB / 13.8MB|2.69GB / 137MB|5
mindscape-ai-local-core-whisper|0.25%|23.7MiB / 15.6GiB|104kB / 126B|3.05GB / 15.7MB|5
source-stack-api-1|12.79%|172.7MiB / 15.6GiB|1.74kB / 126B|7.33GB / 11.9MB|3
mindscape-ai-gpu-executor-redis|0.57%|4.836MiB / 15.6GiB|1.82kB / 126B|1.04GB / 5.75MB|6
mindscape-ai-gpu-executor-postgres|0.05%|10.52MiB / 15.6GiB|1.65kB / 126B|1.89GB / 19.5MB|6
source-stack-redis-1|0.63%|5.746MiB / 15.6GiB|1.95kB / 126B|1.01GB / 5.42MB|6
source-stack-postgres-1|0.07%|8.652MiB / 15.6GiB|1.78kB / 126B|739MB / 15.1MB|6
```

Facts from 1.3:

- The hottest containers during capture were `runner-browser`, `frontend`, `backend-control`, `backend`, and `local-core-postgres`.
- `runner-browser` was the heaviest runtime process in the stack during capture at `3.568GiB / 6GiB`.

## 2. Current IG Runtime Truth

Evidence 2.1 — backend health after transient reset

Commands:

```bash
curl -sS http://127.0.0.1:8200/healthz
curl -sS 'http://127.0.0.1:8200/api/v1/ig/workbench/active-executions?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69&playbook_code_prefix=ig_&limit=20'
curl -sS 'http://127.0.0.1:8200/api/v1/ig/workbench/sidebar-counts?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69'
```

Transient failure seen during collection:

```text
curl: (56) Recv failure: Connection reset by peer
curl: (56) Recv failure: Connection reset by peer
```

Recovered health:

```json
{"status":"ok","backend_role":"execution","reload_enabled":false}
```

Active executions response excerpt:

```json
{
  "running": [
    {
      "id": "091f389b-2abd-4f73-9d0a-ac135cd90a1e",
      "playbook_code": "ig_analyze_following",
      "target": "abadkisser",
      "profile": "/app/data/ig-browser-profiles/walto_lab"
    },
    {
      "id": "e1886252-389e-4350-a28a-692b767cbfcd",
      "playbook_code": "ig_batch_pin_references",
      "target": "ootdsubmit",
      "profile": "/app/data/ig-browser-profiles/default"
    },
    {
      "id": "741b8161-7b01-420d-82f2-fe47488efab8",
      "playbook_code": "ig_analyze_pinned_reference",
      "target": "clio1008",
      "profile": null
    },
    {
      "id": "7d954c3d-1255-4d92-9bbf-7cf3b3daba94",
      "playbook_code": "ig_batch_pin_references",
      "target": "horizontalents",
      "profile": "/app/data/ig-browser-profiles/walto_lab"
    }
  ],
  "total": 20
}
```

Sidebar counts response:

```json
{
  "counts": {
    "total": 140349,
    "completed": 4478,
    "running": 1,
    "pending": 135870,
    "failed": 0
  }
}
```

Facts from 2.1:

- The IG runtime was not idle at capture time. There were at least four running IG executions.
- The count source feeding `sidebar-counts` did not agree with `active-executions` at the same time. Runtime truth said `4` running; sidebar count said `1`.
- During evidence collection the backend briefly reset and then recovered, which explains short-lived `connection reset by peer` errors but does not explain the longer-running count mismatch.

## 3. Runner-Browser Failure Chain

Evidence 3.1 — `runner-browser` log excerpt after restart

Command:

```bash
docker logs --since 30m --tail 220 mindscape-ai-local-core-runner-browser
```

Selected lines:

```text
Task 3d79b407-38a9-4d8a-9ac1-7f929a39eb2e externally failed (Runner no-progress watchdog tripped after 900s (playbook=ig_analyze_following, phase=queue, current_step_index=0, heartbeat_at=2026-04-21T20:47:35.029077+00:00, execution_updated_at=2026-04-21T16:58:23.609902+00:00) (auto-resume #1 queued)) — signalling abort
WARNING:backend.app.runner.task_executor:Runner subprocess exited task_id=f5055968-78b4-4f7a-9cc8-f5d4e9a365ee playbook=ig_batch_pin_references pid=691 exitcode=-9
WARNING:backend.app.runner.task_executor:Task f5055968-78b4-4f7a-9cc8-f5d4e9a365ee failed transiently (attempt 1). NACKing to delayed queue.
WARNING:backend.app.runner.reaper:Requested watchdog abort for stalled runner task task_id=77622d09-ed1c-42f3-97cf-bfcce6eb2c78 playbook=ig_analyze_following execution_id=3d79b407-38a9-4d8a-9ac1-7f929a39eb2e
INFO:backend.app.runner.reaper:[Bridge] Moved 2 tasks from delayed to pending queue.
INFO:capabilities.ig.tools.ig_auto_resume_handler:Auto-resume #2 queued for IG task 77622d09-ed1c-42f3-97cf-bfcce6eb2c78 -> new task 091f389b-2abd-4f73-9d0a-ac135cd90a1e (mode=visit allow_partial_resume=True resume_payload_found=True)
WARNING:backend.app.runner.task_executor:Runner heartbeat touch_visibility done task_id=e1886252-389e-4350-a28a-692b767cbfcd playbook=ig_batch_pin_references beat_seq=2 elapsed_ms=8561 ok=True
WARNING:backend.app.runner.task_executor:Runner heartbeat touch_visibility done task_id=7d954c3d-1255-4d92-9bbf-7cf3b3daba94 playbook=ig_batch_pin_references beat_seq=40 elapsed_ms=9582 ok=True
INFO:backend.app.runner.task_executor:Runner resolved runtime binding task=091f389b-2abd-4f73-9d0a-ac135cd90a1e playbook=ig_analyze_following dispatch_mode=docker_local runtime_id=None site_key=None device_id=None via=task_runtime_affinity
WARNING:backend.app.runner.task_executor:Runner subprocess started task_id=091f389b-2abd-4f73-9d0a-ac135cd90a1e playbook=ig_analyze_following pid=913
```

Facts from 3.1:

- `runner-browser` is not merely idle; it is actively requeueing and auto-resuming IG work.
- There is still real instability in `runner-browser`: watchdog aborts on `ig_analyze_following`, subprocess death with `exitcode=-9` on `ig_batch_pin_references`, and slow heartbeat visibility updates around `8.5s` to `9.5s`.
- The queue bridge is active and moving delayed tasks back to pending.

Evidence 3.2 — already-applied minimal fix for the maintenance-loop crash

Code citation:

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/runner/reaper.py:68-73`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/reaper_admission_release_checks.py:258-289`

Relevant code:

```python
if execution_store is None:
    from backend.app.services.stores.postgres.remaining_stores import (
        PostgresPlaybookExecutionsStore,
    )

    execution_store = PostgresPlaybookExecutionsStore()
```

Regression test result:

Command:

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && PYTHONPATH=/Users/shock/Projects_local/workspace/mindscape-ai-local-core:/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend pytest backend/tests/reaper_admission_release_checks.py -q
```

Output:

```text
......                                                                   [100%]
6 passed, 140 warnings in 2.02s
```

Facts from 3.2:

- The earlier `db_path` maintenance-loop crash was patched and regression-tested.
- That patch explains why `runner-browser` is now able to recover tasks and run work again.
- This fix did not eliminate all IG runtime issues. It only removed one failure mode in the maintenance cycle.

Evidence 3.3 — current browser-runner OOM / concurrency evidence

Commands:

```bash
docker inspect -f '{{.State.OOMKilled}}|{{.State.Status}}|{{.RestartCount}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}' mindscape-ai-local-core-runner-browser
docker exec mindscape-ai-local-core-runner-browser env | rg '^LOCAL_CORE_RUNNER_MAX_INFLIGHT='
docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}' mindscape-ai-local-core-runner-browser
docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select id, pack_id, status, blocked_reason, error, started_at, completed_at, execution_id from tasks where workspace_id = 'bac7ce63-e768-454d-96f3-3a00e8e1df69' and pack_id in ('ig_batch_pin_references','ig_analyze_following') and started_at >= '2026-04-21'::timestamptz order by started_at desc limit 10;"
```

Output excerpts:

```text
true|running|1|6442450944|0
LOCAL_CORE_RUNNER_MAX_INFLIGHT=3
mindscape-ai-local-core-runner-browser|2.949GiB / 6GiB|65.14%
```

```text
a9989f8a-a769-48d0-bb3e-e82932c6bc73 | ig_batch_pin_references | running | ... |
67f47ecd-1e7a-470d-8fc0-5ce4da9be0ce | ig_batch_pin_references | running | ... |
e1886252-389e-4350-a28a-692b767cbfcd | ig_batch_pin_references | failed  | ... | Runner subprocess exited non-zero (exitcode=-9)
7d954c3d-1255-4d92-9bbf-7cf3b3daba94 | ig_batch_pin_references | failed  | ... | Runner subprocess exited non-zero (exitcode=-9)
4834819f-bc95-46f1-9ee2-77d1de179625 | ig_batch_pin_references | failed  | ... | Runner subprocess exited non-zero (exitcode=-9)
```

Facts from 3.3:

- `runner-browser` has confirmed `OOMKilled=true` history.
- The live container is currently configured with `LOCAL_CORE_RUNNER_MAX_INFLIGHT=3`.
- During sampling, the container was already using roughly half of its `6GiB` memory budget.
- `ig_batch_pin_references` has multiple independent task failures with `exitcode=-9`, not a single isolated bad task row.

Evidence 3.4 — startup transport-residue recovery after live fix

Commands:

```bash
docker logs --tail 160 mindscape-ai-local-core-runner-browser
curl -sS 'http://127.0.0.1:8200/api/v1/ig/workbench/active-executions?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69&playbook_code_prefix=ig_&limit=20'
docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select id, pack_id, status, blocked_reason, started_at, completed_at, error from tasks where workspace_id = 'bac7ce63-e768-454d-96f3-3a00e8e1df69' and pack_id in ('ig_batch_pin_references','ig_analyze_following') and started_at >= '2026-04-21 21:15:00+00'::timestamptz order by started_at desc limit 12;"
```

Output excerpts:

```text
INFO:__main__:Local-Core runner started runner_id=f9dec1a09f9c-3db1881d profile=browser_local ... max_inflight=2 ...
INFO:__main__:[Startup] Reset 2 orphaned running task(s)
INFO:__main__:[Startup] Purged 2 stale Redis transport entries for reset task ids=67f47ecd-1e7a-470d-8fc0-5ce4da9be0ce,a9989f8a-a769-48d0-bb3e-e82932c6bc73
INFO:__main__:[Backfill] Enqueued 2/2 runnable pending tasks into shard queues.
WARNING:backend.app.runner.task_executor:Runner subprocess started task_id=39eecb98-e7b1-4ccb-874b-9257cef50154 playbook=ig_batch_pin_references pid=27
WARNING:backend.app.runner.task_executor:Runner subprocess started task_id=ea3e7b5c-9bf1-4607-9243-681ef7427f60 playbook=ig_batch_pin_references pid=30
```

```text
a9989f8a-a769-48d0-bb3e-e82932c6bc73 | ig_batch_pin_references | running | ...
67f47ecd-1e7a-470d-8fc0-5ce4da9be0ce | ig_batch_pin_references | running | ...
```

Facts from 3.4:

- The post-restart stall was caused by stale Redis transport membership for orphaned batch-pin tasks.
- After purging those stale transport entries on startup, the runner backfilled and started the stranded tasks immediately.
- The live browser runner is now running with `max_inflight=2`, and the stranded batch-pin tasks have resumed.

## 4. Backend / UI Mismatch

Evidence 4.1 — code path for sidebar count

Code citations:

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/ig/api/workbench_api_summary_routes.py:135-206`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/ig/api/workbench_api_summary_routes.py:259-264`

Relevant code:

```python
def load_reference_counts(workspace_id: str) -> Dict[str, int]:
    ...
    counts = {
        "total": int(snapshot["total"]),
        "completed": int(snapshot["completed"]),
        "running": 0,
        "pending": int(snapshot["pending"]),
        "failed": int(snapshot["failed"]),
    }
    ...

@router.get("/sidebar-counts")
async def get_sidebar_counts(
    workspace_id: str = Query(..., description="Workspace ID"),
):
    try:
        return {"counts": load_reference_counts(workspace_id)}
```

Evidence 4.2 — code path for active execution list

Code citation:

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/ig/api/workbench_api_data.py:172-268`

Relevant code:

```python
def load_active_executions(
    workspace_id: str,
    *,
    playbook_code_prefix: Optional[str],
    playbook_codes: Optional[Sequence[str]],
    statuses: Optional[Sequence[str]],
    limit: int,
) -> List[Dict[str, Any]]:
    ...
    query = """
        SELECT
            id,
            execution_id,
            parent_execution_id,
            pack_id,
            status,
            created_at,
            started_at,
            completed_at,
            error,
            blocked_reason,
            execution_context
        FROM tasks
        WHERE workspace_id = :workspace_id
          AND status IN :statuses
```

Evidence 4.3 — zero-extra-request UI reconciliation already staged

Code citation:

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/capabilities/ig/components/workbench/hooks/useIGWorkbenchState.ts:36-40`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/capabilities/ig/components/workbench/hooks/useIGWorkbenchState.ts:323-334`

Relevant code:

```ts
function countDisplayActiveRuns(runs: any[]): number {
  return (Array.isArray(runs) ? runs : []).filter((run) => {
    const status = (run?.status || '').toString().toLowerCase();
    return status === 'running' || status === 'queued' || status === 'paused';
  }).length;
}

const loadRecentRuns = useCallback(async (force = false) => {
  const [counts, nextRuns] = await Promise.all([
    fetchRunLogCounts(force),
    fetchRecentRuns(force),
  ]);
  if (!counts || !nextRuns) return;
  applyRunLogCounts({
    ...counts,
    running: countDisplayActiveRuns(nextRuns),
  });
}, [applyRunLogCounts, fetchRecentRuns, fetchRunLogCounts]);
```

Facts from 2.1 + 4.1 + 4.2 + 4.3:

- The `ACTIVE RUNS` count and the active run cards were backed by different datasets.
- `sidebar-counts` is reference-count-driven.
- `active-executions` is task-table-driven.
- The staged UI fix does not add any new frontend request. It reuses the existing `sidebar-counts` and `active-executions` fetches, then overrides only the displayed `running` count with the already-fetched execution rows.

## 5. Backend Restart Window

Evidence 5.1 — backend startup log

Command:

```bash
docker logs --since 30m --tail 180 mindscape-ai-local-core-backend
```

Selected lines:

```text
2026-04-21 20:49:32,902 - backend.app.app_bootstrap.lifecycle - INFO - Application startup hook entered (pid=1)
2026-04-21 20:49:33,172 - backend.app.app_bootstrap.lifecycle - INFO - Zombie task reaper started (interval: 5 minutes)
2026-04-21 20:49:34,006 - backend.app.app_bootstrap.lifecycle - INFO - Pending pack validations resume task scheduled
2026-04-21 20:49:34,010 - backend.app.app_bootstrap.lifecycle - INFO - Tool RAG post-ready warm-up task scheduled
2026-04-21 20:49:35,832 - backend.app.services.capability_registry - INFO - Loaded capability: ig (38 tools)
2026-04-21 20:50:00,618 - backend.app.services.playbook_registry - INFO - Loading capability pack: ig
2026-04-21 20:50:00,928 - backend.app.services.playbook_registry - INFO - Loaded 126 playbooks from ig
```

Facts from 5.1:

- The backend restarted during this audit window.
- The brief `curl: (56) Recv failure: Connection reset by peer` events were consistent with this restart.
- The backend recovered and reloaded the IG capability pack.

## 6. Cloud Postgres Misrouted Traffic

Evidence 6.1 — `source-stack-postgres-1`

Command:

```bash
docker logs --since 12h --tail 200 source-stack-postgres-1
```

Output excerpt:

```text
2026-04-21 20:15:07.109 UTC [96837] FATAL:  database "mindscape" does not exist
2026-04-21 20:15:17.178 UTC [96844] FATAL:  database "mindscape" does not exist
2026-04-21 20:15:27.436 UTC [96851] FATAL:  database "mindscape" does not exist
2026-04-21 20:15:37.513 UTC [96858] FATAL:  database "mindscape" does not exist
2026-04-21 20:15:47.559 UTC [96865] FATAL:  database "mindscape" does not exist
... repeated every ~10s ...
```

Fact:

- Something is repeatedly connecting to `source-stack-postgres-1` using a non-existent database name `mindscape`.

Inference:

- This is likely a misconfigured health check or a misconfigured client outside the local-core IG path. It is noisy and real, but not yet proven to be the direct cause of the IG workbench symptom.

## 7. Exited / Dormant Containers

Evidence from 1.1 + 1.2:

- `mindscape-ai-local-core-ocr` is exited and unhealthy.
- `mindscape-ai-gpu-executor-backend` is only `created`.
- `site-hub-gsm-agent-1`, `site-hub-site-hub-registry-api-1`, `site-hub-site-hub-redis-1`, and `site-hub-registry-db-1` are exited and stale.

Facts:

- OCR is not currently provided by a running Docker container in this stack.
- The GPU executor backend is not currently serving anything.
- There are stale unrelated `site-hub` containers on the host.

## 8. Quiet Containers in This Sample

Sampled tails for these returned no notable recent log lines during this audit window:

- `source-stack-redis-1`
- `mindscape-ai-gpu-executor-redis`

## 9. Applied Fixes As Of 2026-04-22

Code citations:

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/runner/reaper.py:44-205`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/reaper_admission_release_checks.py:138-341`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/capabilities/ig/components/workbench/hooks/useIGWorkbenchState.ts:36-40`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/capabilities/ig/components/workbench/hooks/useIGWorkbenchState.ts:230-335`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docker-compose.yml:345-354`

Facts:

- The no-progress watchdog path now uses the Postgres execution store by default and reads `ig_analyze_following` semantic progress from progress artifacts before aborting a task.
- The workbench hook now keeps the displayed `running` count aligned with the already-fetched active execution rows without increasing frontend polling or request count.
- The browser-runner compose default has been lowered from `3` to `2` inflight tasks because the live runtime is currently at `6GiB` memory limit with confirmed `OOMKilled=true` history.
- Startup recovery now purges stale Redis transport entries for orphaned runner tasks before startup backfill, which fixes the “reset to pending but never re-enqueued” failure mode.
- `mindscape-ai-gpu-executor-postgres`

This does not prove they are healthy in all dimensions. It only means this audit did not catch active errors from their sampled tails.

## 9. Conclusions

Facts:

1. The system was not globally idle. IG work was actively running during capture.
2. The earlier `runner-browser` maintenance-loop crash was real, was fixed, and the fix is tested.
3. The current live symptom is now a combination of:
   - real `runner-browser` instability on some IG workloads, and
   - a backend/UI truth mismatch between `active-executions` and `sidebar-counts`.
4. The backend also restarted during the audit window, causing transient fetch resets.
5. `source-stack-postgres-1` is receiving repeated bad connections to the nonexistent DB `mindscape`.
6. `mindscape-ai-local-core-ocr` is not running.

Open repair items:

1. Unify the sidebar `running` count with the same execution truth used by `/active-executions`, or explicitly relabel the card if it is intentionally reference-count-based.
2. Trace why `ig_analyze_following` tasks still sit in `phase=queue` long enough to trip the no-progress watchdog.
3. Trace why some `ig_batch_pin_references` subprocesses are still dying with `exitcode=-9`.
4. Identify the caller hitting `source-stack-postgres-1` with `database "mindscape"` and fix or silence it.
5. Decide whether `mindscape-ai-local-core-ocr` should be restored or its dependent OCR paths should be hard-disabled.

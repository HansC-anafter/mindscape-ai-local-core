# IG Vision Analyze MLX Route Repair Report - Corrected 2026-05-06

## Status

This report replaces the earlier 2026-05-05 recovery report. The earlier Qwen2.5 live-completion evidence is removed from this document because it is not an acceptable closure baseline for Analyze Pinned Reference.

The required baseline is:

- Runtime model: `mlx-community/Qwen3.5-9B-4bit`
- Profile: `visual_anatomy`
- Output budget: `max_tokens = 12288` and `max_output_tokens = 12288`
- Routing authority: `model-routing-registry`

`12288` is the current quality/time baseline. It is not a defect, not an oversized-output finding, and not a valid default remediation target.

## Corrected Findings

### F1. The active route is Qwen3.5 through the model-routing registry.

> **Evidence**: `docker exec mindscape-ai-local-core-runner-vision python -c "from backend.app.capabilities.core_llm.services import multimodal; r=multimodal._resolve_vision_route(); print(r[0]); print(r[1]); print(multimodal._resolve_multimodal_base_url(r[2]))"`
> ```
> mlx-community/Qwen3.5-9B-4bit
> mlx
> http://host.docker.internal:8210
> ```

### F2. The Qwen3.5 model metadata intentionally keeps the 12288 output budget.

> **Evidence**: `curl -sS http://localhost:8300/api/v1/system-settings/models | jq '.[]? | select(.model_name=="mlx-community/Qwen3.5-9B-4bit") | {model_name, metadata}'`
> ```json
> {
>   "model_name": "mlx-community/Qwen3.5-9B-4bit",
>   "metadata": {
>     "runtime_engine": "mlx",
>     "runtime_provider": "mlx",
>     "base_url": "http://host.docker.internal:8210",
>     "openai_base_url": "http://host.docker.internal:8210",
>     "max_output_tokens": 12288,
>     "local_max_output_tokens_cap": 12288
>   }
> }
> ```

### F3. The current runtime failure class is late MLX success after runner timeout, not a token-budget defect.

Recent Qwen3.5 runs show MLX completing successfully after a long generation, but the runner has already recorded `provider_unavailable` for that attempt. This creates failed workflow state even when MLX later logs `POST /v1/chat/completions 200 OK`.

> **Evidence**: `tail -n 160 scripts/mlx-server/logs/mlx-server.log`
> ```
> [mlx-watchdog] Health check failed but inflight request is still active (...) - not counting
> Generation finished, cleared cache.
> INFO:     127.0.0.1:64144 - "POST /v1/chat/completions HTTP/1.1" 200 OK
> ```

> **Evidence**: `docker logs --tail 1200 mindscape-ai-local-core-runner-vision`
> ```
> [MultimodalAnalyze] Multimodal endpoint call failed for DGe6ayutdH8:
> Step vision_analyze failed: Step vision_analyze recoverable error [provider_unavailable]: Multimodal endpoint unreachable or returned no results
> Step ig_analyze_pinned_reference failed after retries, stopping workflow
> ```

### F4. The watchdog repair direction is correct but incomplete.

The runner now writes a host-visible inflight state file, and the host watchdog recognizes active Qwen3.5 generation instead of killing MLX solely because `/v1/models` is blocked during inference.

> **Evidence**: `cat /Volumes/OWC\ Ultra\ 4T/mindscape-ai-local-core-runtime/data/runtime/mlx-watchdog/inflight_request.json`
> ```json
> {
>   "status": "active",
>   "phase": "generating",
>   "model": "mlx-community/Qwen3.5-9B-4bit"
> }
> ```

> **Evidence**: `tail -n 160 scripts/mlx-server/logs/mlx-server.log`
> ```
> [mlx-watchdog] Health check failed but inflight request is still active (...) - not counting
> ```

### F5. First Qwen3.5 / 12288 success is now verified.

The repaired path completed a real Analyze Pinned Reference run with the required Qwen3.5 / visual_anatomy / 12288 baseline.

> **Evidence**: `jq '{reference_id, source_shortcode, job_status:(.analysis_job.status // null), has_vision:(.vision_description != null), has_training:(.training_annotations != null), provenance:.analysis_provenance, raw_len:(.analysis_debug.raw_text | length), thinking_len:(.analysis_debug.thinking_text | length), failure_stage:(.analysis_debug.failure_stage // null), finish_reason:(.analysis_debug.transport_finish_reason // null)}' '/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@17.chien/DFiJGxjT9ec.json'`
> ```json
> {
>   "reference_id": "ref_b3f43990",
>   "source_shortcode": "DFiJGxjT9ec",
>   "job_status": "COMPLETED",
>   "has_vision": true,
>   "has_training": true,
>   "provenance": {
>     "schema_version": "2.1",
>     "validated_at": "2026-05-06T05:05:45.380074Z",
>     "analysis_profile": "visual_anatomy",
>     "prompt_version": "v2.1"
>   },
>   "raw_len": 33235,
>   "thinking_len": 27241,
>   "failure_stage": "",
>   "finish_reason": "stop"
> }
> ```

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select id, status, completed_at, error from tasks where id='e7747ac5-0e77-4fe9-866f-b563200eaed9';"`
> ```
> id                                   | status    | completed_at                  | error
> e7747ac5-0e77-4fe9-866f-b563200eaed9 | succeeded | 2026-05-06 05:10:46.595713+00 |
> ```

### F6. Run Logs lifecycle event is now verified for the successful run; failure event paths are patched.

The completed run emitted `run_state_changed` with `new_state=DONE`. A follow-up code fix also changes the event helper to use `execution_context.inputs` when `task.params` is empty, so future success/failure events carry the reference context instead of dropping it.

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select timestamp, event_type, payload::jsonb->>'execution_id' as execution_id, payload::jsonb->>'new_state' as new_state, payload::jsonb->>'playbook_code' as playbook_code, payload::jsonb->>'reference_id' as reference_id from mind_events where event_type='run_state_changed' and payload::jsonb->>'execution_id'='e7747ac5-0e77-4fe9-866f-b563200eaed9' order by timestamp desc limit 10;"`
> ```
> timestamp                  | event_type        | execution_id                          | new_state | playbook_code                | reference_id
> 2026-05-06 05:10:46.680033 | run_state_changed | e7747ac5-0e77-4fe9-866f-b563200eaed9 | DONE      | ig_analyze_pinned_reference |
> ```

### F7. The remaining slowdown after MLX completion was a 321M file-index write path.

After the first ref metadata completed, the task stayed running while the catalog entry/index caught up. The file index is `321M`, and the old `add_entry()` path read and rewrote that full JSON index for one completed reference. The repaired path now defaults the reference catalog to DB mode and skips the full JSON rewrite when the DB catalog is available.

> **Evidence**: `du -h '/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/_index.json' '/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/_index.summary.json' '/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/_index.counts.json'`
> ```
> 321M  _index.json
> 8.4M  _index.summary.json
> 236K  _index.counts.json
> ```

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select count(*) as rows, count(*) filter (where workspace_id='bac7ce63-e768-454d-96f3-3a00e8e1df69') as bac7_rows from ig_reference_catalog;"`
> ```
> rows   | bac7_rows
> 160400 | 160398
> ```

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select reference_id, analysis_status, analysis_job_status, has_analysis, validated_at from ig_reference_catalog where workspace_id='bac7ce63-e768-454d-96f3-3a00e8e1df69' and reference_id='ref_b3f43990';"`
> ```
> reference_id | analysis_status | analysis_job_status | has_analysis | validated_at
> ref_b3f43990 | COMPLETED       | COMPLETED           | t            | 2026-05-06 05:05:45.380074+00
> ```

> **Evidence**: `curl -sS 'http://localhost:8300/api/v1/ig/workbench/sidebar-counts?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69'`
> ```json
> {"counts":{"total":160397,"completed":6597,"running":1,"pending":153797,"failed":2}}
> ```

## Files Changed In This Repair Pass

- [backend/app/capabilities/core_llm/services/multimodal.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/core_llm/services/multimodal.py) writes shared MLX inflight heartbeat state and resolves Qwen3.5 through registry metadata.
- [scripts/mlx-server/start-mlx-server.sh](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/scripts/mlx-server/start-mlx-server.sh) reads the shared inflight state before counting a failed health check against MLX.
- [scripts/mlx-server/watchdog_state.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/scripts/mlx-server/watchdog_state.py) validates whether a runner request is actively heartbeating.
- [backend/app/capabilities/core_files/services/ocr_client.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/core_files/services/ocr_client.py) prevents missing default `ocr-service` DNS from forcing Analyze Pinned Reference failure when OCR is not configured.
- [backend/app/runner/task_executor.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/runner/task_executor.py) emits terminal `run_state_changed` events and now falls back to `execution_context.inputs` when `task.params` is empty.
- [backend/app/runner/reaper.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/runner/reaper.py) emits `run_state_changed` for stale/terminal failed task recovery and now uses the same non-empty input resolution.
- [backend/app/capabilities/ig/services/reference_catalog_config.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/ig/services/reference_catalog_config.py) defaults the reference catalog to DB mode.
- [backend/app/capabilities/ig/services/reference_index_write.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/ig/services/reference_index_write.py) writes single-entry updates to DB catalog and skips full `_index.json` rewrites when DB reads are active.
- [capabilities/ig/services/reference_catalog_config.py](/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/services/reference_catalog_config.py) applies the same DB-mode default in the IG capability source.
- [capabilities/ig/services/reference_index_write.py](/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/services/reference_index_write.py) applies the same DB-catalog single-entry write in the IG capability source.

## Open Work

1. Let the currently running `ref_045b352f` finish without restart, then verify that DB-catalog single-entry write removes the post-MLX 321M index rewrite delay.
2. Validate the next real failed Analyze Pinned Reference event after the patched parent process is reloaded; the success event is verified, and failed/reaper event code paths are patched but should still be checked against a real failure.
3. Keep `12288` as the Qwen3.5 baseline unless a separate quality-preserving evidence pass proves a better value.

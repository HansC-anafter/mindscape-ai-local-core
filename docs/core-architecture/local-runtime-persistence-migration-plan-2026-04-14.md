# Local Runtime Persistence Migration Plan (2026-04-14)

## Backup First

Before any code change, config change, symlink swap, or data move, create backups.

PostgreSQL backup:

```bash
docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_test_$(date +%Y%m%d_%H%M%S).sql
```

Filesystem backups for the current live roots:

```bash
mkdir -p data/backups/runtime-fs
rsync -aH "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/" "data/backups/runtime-fs/secrets_pre_migration/"
rsync -aH "/Users/shock/.mindscape/storage/" "data/backups/runtime-fs/storage_pre_migration/"
rsync -aH "/Users/shock/.mindscape/models/" "data/backups/runtime-fs/models_pre_migration/"
```

Config backups:

```bash
cp docker-compose.yml "data/backups/docker-compose.pre_migration.$(date +%Y%m%d_%H%M%S).yml"
cp .env "data/backups/.env.pre_migration.$(date +%Y%m%d_%H%M%S)"
```

## Phase 1: Evidence Collection

### Evidence items

- **E1. Compose currently mounts a mixed `.mindscape` tree.** `docker-compose.yml:41-49` mounts `/root/.mindscape` from `${LOCAL_CORE_SECRETS_HOST_DIR}`, then shadows `/root/.mindscape/models` and `/root/.mindscape/storage` from separate host roots. The backend service repeats the same pattern at `docker-compose.yml:155-163`.
- **E2. Live backend confirms the mixed mount topology.** `docker inspect mindscape-ai-local-core-backend --format '{{json .Mounts}}'` returned:
  - `/root/.mindscape <- /Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets`
  - `/root/.mindscape/models <- /Users/shock/.mindscape/models`
  - `/root/.mindscape/storage <- /Users/shock/.mindscape/storage`
- **E3. Live backend does not set `WORKSPACE_STORAGE_ROOT`.** `docker inspect mindscape-ai-local-core-backend --format '{{json .Config.Env}}'` showed `LOCAL_STORAGE_PATH=/root/.mindscape/storage/layer_asset_forge`, but no `WORKSPACE_STORAGE_ROOT`.
- **E4. Workspace storage falls back to `HOME/.mindscape/workspaces` when `WORKSPACE_STORAGE_ROOT` is unset.** `mindscape-ai-cloud/capabilities/ig/services/workspace_storage.py:137-145` resolves workspace storage from `WORKSPACE_STORAGE_ROOT`, else `Path.home() / ".mindscape" / "workspaces"`. `mindscape-ai-cloud/capabilities/ig/manifest.yaml:29-34` encodes the same fallback.
- **E5. Additional packs also default workspace paths from `HOME`.** `mindscape-ai-cloud/services/multi_site/workspace_site_store.py:30-38` and `mindscape-ai-cloud/capabilities/web_generation/api/dependencies.py:86-92` both fall back to `~/.mindscape/workspaces`.
- **E6. Layer Asset Forge storage is container-visible via `LOCAL_STORAGE_PATH`.** `mindscape-ai-cloud/capabilities/layer_asset_forge/services/storage_service.py:25-35` roots storage under `LOCAL_STORAGE_PATH`.
- **E7. Task execution state is durable in Postgres, not only in process memory.** `backend/app/services/stores/tasks_store/_runner.py:106-175` persists task claim state and `backend/app/services/stores/tasks_store/_runner.py:177-247` persists runner heartbeats into the task row.
- **E8. Redis is used as a transport queue, and the local compose config explicitly disables AOF persistence.** `docker-compose.yml:304-315` runs Redis with `--appendonly no`.
- **E9. Runner startup explicitly reconstructs transport state from Postgres after restart.** `backend/app/runner/worker.py:93-105` documents that Redis has no persistence and pending tasks must be re-enqueued from Postgres. `backend/app/runner/worker.py:480-486` resets orphaned running tasks, backfills pending tasks, and cleans stale locks on startup.
- **E10. Reaper logic is designed for recovery, not transparent continuity.** `backend/app/runner/reaper.py:279-387` requeues stale queued tasks and applies a rolling-restart grace period, but this is still recovery after ownership changed.
- **E11. Runner restart only drains inflight work for 30 seconds before forced exit.** `backend/app/runner/restart.py:12-13` sets `_RESTART_DRAIN_TIMEOUT_SECONDS = 30`; `backend/app/runner/worker.py:529-559` waits up to that timeout, then exits.
- **E12. Playbook initializer artifacts are outside the `.mindscape` runtime tree.** `backend/app/services/playbook_run_executor.py:152-155` initializes `PlaybookInitializer("/tmp/mindscape-workspace")`, and `backend/app/services/playbook_initializer.py:62-79` writes progress files there. Not every execution artifact is part of the `.mindscape` migration scope.
- **E13. Host-runtime storage/model resolution is only partially parameterized today.**
  - `mindscape-ai-cloud/capabilities/layer_asset_forge/services/host_runtime_bridge.py:66-70` supports `MINDSCAPE_STORAGE_HOST_DIR`.
  - `mindscape-ai-local-core/scripts/laf_host_runtime_common.py:90-95` supports `MINDSCAPE_MODEL_ROOT`.
  - However, `mindscape-ai-cloud/capabilities/layer_asset_forge/services/host_runtime_bridge.py:125-175` builds host commands with `--runtime-root` only; it does not inject `MINDSCAPE_MODEL_ROOT` or `MINDSCAPE_STORAGE_HOST_DIR` into the host process environment.
- **E14. Several model-related paths still hardcode `~/.mindscape/models`.**
  - `backend/app/services/model_weights_installer.py:209-220`
  - `mindscape-ai-cloud/capabilities/layer_asset_forge/services/model_provider.py:338-360`
  - `mindscape-ai-cloud/capabilities/layer_asset_forge/services/model_provider.py:475-558`
  - `mindscape-ai-cloud/capabilities/layer_asset_forge/model-manifest.yaml:345`
  - `backend/app/schema/model_manifest_schema.py:167-172`
- **E15. Device Node governance currently allowlists `~/.mindscape/models` and `~/.mindscape/runtimes`, not an external-drive path.**
  - `device-node/src/governance/permission-map.ts:74-81`
  - `device-node/config/permissions.yaml:16-21`
- **E16. Current live system is not idle.** Runtime queries collected on `2026-04-14` were a point-in-time snapshot:
  - `SELECT status, COUNT(*) FROM tasks GROUP BY status` => `pending=125719`, `running=5`, `failed=5290`, `succeeded=23737`, `cancelled_by_user=264`
  - `SELECT runner_id, profile_code, inflight, heartbeat_at FROM runner_heartbeats ...` => current heartbeats reported `vision_local inflight=3`, `browser_local inflight=2`, `default_local inflight=0`
  - `redis-cli ZCARD mindscape:queue:processing:vision_local` => `3`
  - `redis-cli ZCARD mindscape:queue:processing:browser_local` => `2`
  - `redis-cli LLEN mindscape:queue:pending:{default_local,vision_local,browser_local}` => `0`, confirming the hot queue is empty while the authoritative pending backlog remains in Postgres.
- **E16a. The live counts above are not stable constants.** Re-querying the same runtime later on `2026-04-14` already showed drift (`pending=125735`, `running=4`, `failed=5307`, `succeeded=23740`, `cancelled_by_user=268`; active `inflight` at `browser_local=3`, `vision_local=1`, `default_local=0`; Redis `processing` at `browser_local=3`, `vision_local=1`, `default_local=0`). Cutover gates must therefore use live re-queries, not the earlier snapshot.
- **E17. There is no verified repo-wide maintenance-mode or global ingress-freeze switch.** A full-project grep across `backend/app` for `maintenance mode`, `freeze ingress`, `disable submissions`, `pause ingestion`, and related terms only found queue admission and restart helpers, not a general-purpose global freeze endpoint.
- **E18. Current architecture target already recommends a single runtime host root and explicit envs.** `docs/core-architecture/local-runtime-persistence-topology.md:182-214` recommends a single `LOCAL_CORE_RUNTIME_ROOT_HOST_DIR` with explicit `WORKSPACE_STORAGE_ROOT`, `LOCAL_STORAGE_PATH`, `MINDSCAPE_MODEL_ROOT`, and `MINDSCAPE_RUNTIME_ROOT`.
- **E19. Installed capability code under `backend/app/capabilities/*` is the live runtime source of truth.**
  - `backend/app/routes/core/capability_packs.py:218-231` scans installed packs from `backend/app/capabilities`.
  - `backend/app/routes/core/tools/base.py:62-80` explicitly treats installed manifests in `backend/app/capabilities/*/manifest.yaml` as the install SOT during fallback tool loading.
- **E20. The Layer Asset Forge host-runtime bridge resolves host scripts from the installed local-core pack surface.** `backend/app/capabilities/layer_asset_forge/services/host_runtime_bridge.py:693-710` prefers `LOCAL_CORE_PROJECT_ROOT/backend/app/capabilities/layer_asset_forge/scripts/*` when `LOCAL_CORE_PROJECT_ROOT` is a host-style path.
- **E21. Device Node `shell_execute` does not support per-command environment injection.**
  - `device-node/src/mcp-server.ts:109-126` exposes `command`, `args`, `cwd`, and `timeout_ms`.
  - `device-node/src/capabilities/shell.ts:101-166` spawns the child with those fields only; there is no `env` argument in the tool contract.
- **E22. The verified host-runtime root env today is `LAF_HOST_RUNTIME_ROOT`, not `MINDSCAPE_RUNTIME_ROOT`.**
  - `backend/app/capabilities/layer_asset_forge/services/host_runtime_bridge.py:44-49` reads `LAF_HOST_RUNTIME_ROOT`.
  - `backend/app/capabilities/layer_asset_forge/scripts/laf_host_runtime_common.py:94-109` resolves host runtime/model roots from `LAF_HOST_RUNTIME_ROOT` and `MINDSCAPE_MODEL_ROOT`.
  - `MINDSCAPE_RUNTIME_ROOT` exists as an architecture target in docs, but is not yet a verified live host-runtime control knob.
- **E23. The installed pack copies in local-core still contain the same home-path fallbacks that exist in cloud source today.**
  - `backend/app/capabilities/ig/services/workspace_storage.py:137-145`
  - `backend/app/capabilities/web_generation/api/dependencies.py:86-92`
  - `backend/app/capabilities/layer_asset_forge/services/model_provider.py:338-360`
  - `backend/app/capabilities/layer_asset_forge/model-manifest.yaml:345`
- **E24. Live runner profiles are separate containers and also lack the explicit path envs today.**
  - `docker inspect mindscape-ai-local-core-runner-default --format '{{json .Config.Env}}'` and `docker inspect mindscape-ai-local-core-runner-browser --format '{{json .Config.Env}}'` showed `LOCAL_STORAGE_PATH`, but no `WORKSPACE_STORAGE_ROOT` or `MINDSCAPE_MODEL_ROOT`.
  - `docker inspect mindscape-ai-local-core-runner-default --format '{{json .Mounts}}'` showed the same mixed mount topology as the backend.

## Phase 1.5: Historical Regression Analysis

### H1. Split `models` and `storage` mounts were introduced for host-runtime bridging

- Commit `d0dca3e` (`feat(runtime): add host layer asset forge runtime bridge`) added:
  - `LOCAL_STORAGE_PATH=/root/.mindscape/storage/layer_asset_forge`
  - `${MINDSCAPE_MODELS_HOST_DIR:-${HOME}/.mindscape/models}:/root/.mindscape/models`
  - `${MINDSCAPE_STORAGE_HOST_DIR:-${HOME}/.mindscape/storage}:/root/.mindscape/storage`
- Evidence: `git show d0dca3e -- docker-compose.yml`
- Rationale at the time: keep host Layer Asset Forge model/storage assets visible from the existing host `~/.mindscape/*` tree.
- Structural limitation: only `models` and `storage` were split out; `workspaces` remained under `/root/.mindscape` from the base secrets mount.

### H2. The runtime root was later externalized only partially

- Commit `32c4c01` (`feat: evolve local host orchestration, runtime, and store surfaces`) changed `./data`, `./data/secrets`, `./logs`, and `./data/postgres` into env-driven external roots, but retained the separate `MINDSCAPE_MODELS_HOST_DIR` and `MINDSCAPE_STORAGE_HOST_DIR` mounts.
- Evidence: `git show 32c4c01 -- docker-compose.yml`
- Rationale at the time: move runtime data/logs/postgres onto configurable host directories without disturbing the existing host-runtime bridge.
- Why the current topology is still split: the change externalized `data` and `secrets` but did not realign the later-added `models` and `storage` subtrees under the same host root.

### H3. Runner recovery logic already assumes restart-and-recover, not transparent continuity

- Commits `a29e90f` and `32c4c01` added frontier scheduling, Redis reconciliation, recovery backfill, rolling-restart grace handling, and stale-task requeue logic.
- Evidence: `git show a29e90f -- backend/app/runner/reaper.py`, `git show 32c4c01 -- backend/app/runner/task_executor.py backend/app/services/stores/tasks_store/_runner.py backend/app/services/stores/redis/runner_queue_store.py`
- Structural lesson: the system is engineered to recover from runner/backend restarts, but not to preserve an arbitrary long-running subprocess across a mount swap.

## Phase 2: Problem Definition + Severity Scoring

1. **[Split runtime roots produce inconsistent data visibility]** `workspaces`, `storage`, and `models` are not sourced from the same host tree, so sibling paths under `.mindscape` do not mean the same thing at runtime. (E1, E2, E3, E4, E5)
2. **[Mount cutover cannot preserve active subprocess continuity]** Changing bind mounts requires backend/runner container recreation, and runner restart logic is recovery-oriented with a 30-second drain ceiling, not a guarantee that in-flight subprocesses survive unchanged. (E7, E8, E9, E10, E11, E16)
3. **[Waiting for the full pending backlog to drain is operationally infeasible]** The live backlog is `125719` pending tasks; the correct cutover gate is `running/inflight/processing=0`, not `pending=0`, because pending tasks are durable in Postgres and repopulated on restart. (E8, E9, E16)
4. **[No verified ingress freeze means late writes can land in the old roots during final sync]** Without a global maintenance switch, producers can continue creating tasks or artifacts while the final delta copy runs. (E16, E17)
5. **[Host-runtime, runner, and device-node path contract is incomplete]** Even if compose mounts move cleanly, host-side runtime execution, runner containers, and device-node governance will drift unless compatibility or explicit env propagation is handled across the whole execution path. (E13, E14, E15, E21, E22, E24)
6. **[Cloud source changes do not automatically update the live installed pack surface]** If migration-related capability code changes land only in `mindscape-ai-cloud`, the live local-core runtime may continue using stale installed copies under `backend/app/capabilities/*`. (E19, E20, E23)
7. **[Not all execution artifacts live under `.mindscape`]** A full migration narrative that assumes all runtime state is inside `.mindscape` is wrong; some playbook initializer artifacts are still under `/tmp/mindscape-workspace`. (E12)

### FMEA-lite

| Problem | Severity | Detection | Priority |
| --- | --- | --- | --- |
| #2 Mount cutover cannot preserve active subprocess continuity | 5 | 4 | 20 |
| #1 Split runtime roots produce inconsistent data visibility | 4 | 4 | 16 |
| #4 No verified ingress freeze means late writes can land in the old roots | 4 | 4 | 16 |
| #3 Waiting for the full pending backlog to drain is infeasible | 5 | 3 | 15 |
| #5 Host-runtime, runner, and device-node path contract is incomplete | 4 | 3 | 12 |
| #6 Cloud source changes do not automatically update the live installed pack surface | 4 | 3 | 12 |
| #7 Not all execution artifacts live under `.mindscape` | 2 | 3 | 6 |

## Phase 3: Assumption Verification (CoVe)

| Assumption | Verification question | Answer |
| --- | --- | --- |
| Pending backlog must be fully drained before cutover | Does startup rehydrate pending work from durable state after restart? | Yes. `backend/app/runner/worker.py:93-105` and `backend/app/runner/worker.py:480-486` explicitly backfill pending tasks from Postgres. |
| Running work can be swapped over transparently | Is there code that preserves a live subprocess across runner/backend recreation? | No. The runner only waits up to 30 seconds and then exits. Recovery is requeue/reset based. `backend/app/runner/restart.py:12-13`, `backend/app/runner/worker.py:529-559`, `backend/app/runner/reaper.py:279-387`. |
| Workspace root is already explicitly configured | Does live backend export `WORKSPACE_STORAGE_ROOT`? | No. `docker inspect` env output had no `WORKSPACE_STORAGE_ROOT`, and the code falls back to `HOME/.mindscape/workspaces`. (E3, E4) |
| Host-runtime model root is already propagated by the bridge | Does the bridge pass `MINDSCAPE_MODEL_ROOT` into host commands? | Not in the verified command builder path. `host_runtime_bridge.py:125-175` only passes `--runtime-root`. |
| Changing cloud repo source is enough for the live rollout | Does local-core execute those packs directly from the cloud repo working tree? | No. The live runtime source of truth is the installed copy under `backend/app/capabilities/*`, and host-runtime script resolution explicitly points there. (E19, E20, E23) |
| Device Node can inject per-command env vars for host-runtime fixes | Does `shell_execute` accept an `env` payload? | No. The verified tool contract only supports `command`, `args`, `cwd`, and `timeout_ms`. (E21) |
| `MINDSCAPE_RUNTIME_ROOT` is the verified host-runtime env for Stage A | Do current LAF host-runtime scripts read `MINDSCAPE_RUNTIME_ROOT`? | No. The verified live env name is `LAF_HOST_RUNTIME_ROOT`; `MINDSCAPE_RUNTIME_ROOT` is only the architecture target today. (E22) |
| Backend-only validation is sufficient | Are runners guaranteed to inherit the same env/mount contract without explicit verification? | No. Runners are separate containers and the live runner env currently lacks the new explicit path vars. (E24) |
| There is a general ingress freeze switch | Does a full-project grep reveal a maintenance-mode or freeze endpoint? | No verified global switch was found in `backend/app`. The existing admission service is backpressure logic, not a full freeze. (E17) |
| The migration scope is exactly `.mindscape/*` | Are all execution artifacts under `.mindscape`? | No. The playbook initializer still writes under `/tmp/mindscape-workspace`. (E12) |

## Phase 3.5: Pre-Mortem

### Failure mode 1: final delta sync misses late writes

- Likely cause: no ingress freeze while `rsync` final pass is running.
- Evidence ruling it out: none.
- Required mitigation: explicit drain window with backend/API maintenance or another verified producer freeze before the final sync.

### Failure mode 2: active browser/vision jobs get killed mid-flight

- Likely cause: containers are recreated while `runner_heartbeats.inflight > 0` or Redis processing ZSETs are non-zero.
- Evidence ruling it out: none. Live state already shows `5` active running tasks. (E16)
- Required mitigation: do not cut over until `tasks.status='running' = 0`, all current runner heartbeats show `inflight=0`, and all processing ZSETs are `0`.

### Failure mode 3: host-runtime model access breaks after mount switch

- Likely cause: device-node permissions and host-runtime defaults still target `~/.mindscape/models`.
- Evidence ruling it out: none. Current allowlists explicitly name `~/.mindscape/models/**`. (E15)
- Required mitigation: either keep a compatibility path at `~/.mindscape/models` during phase 1, or update the host-runtime/device-node permission surface in the same rollout.

### Failure mode 4: repo changes land in cloud source, but live local-core still executes stale installed pack code

- Likely cause: the rollout updates `mindscape-ai-cloud` only and skips `.mindpack` installation into local-core.
- Evidence ruling it out: none. Installed pack directories under `backend/app/capabilities/*` are the live install surface. (E19, E20, E23)
- Required mitigation: if any migration-related pack code changes are part of the rollout, include package + install + installed-copy verification in the same SOP.

### Failure mode 5: validation passes on backend/default runner, but browser or vision runners still point at old roots

- Likely cause: only backend or one runner profile is inspected after recreate.
- Evidence ruling it out: none. Runners are separate containers and current live runner envs are not explicitly aligned yet. (E24)
- Required mitigation: inspect backend plus every live runner profile (`default`, `browser`, `vision`) after recreate.

## Phase 4: Implementation Plan

### Recommended migration strategy

Use a **two-stage migration**:

1. **Stage A: Operational unification now**
   - Goal: remove the runtime split between `workspaces` vs `storage/models` with the smallest live blast radius.
   - Change scope: move `storage` and `models` onto the same external-drive family as `workspaces`, make `WORKSPACE_STORAGE_ROOT` explicit, and preserve host compatibility for model/runtime code that still expects `~/.mindscape/*`.
2. **Stage B: Semantic cleanup later**
   - Goal: finish the architectural rename to a single clean `LOCAL_CORE_RUNTIME_ROOT_HOST_DIR/mindscape/*` tree after the remaining host-runtime/device-node/home-path assumptions are formally retired.

This plan intentionally does **not** recommend a one-shot rename of every root in the same cutover.

### Stage A: Operational unification now

#### A1. Define the target roots and compatibility boundary

Resolves Problem #1, #5.

Target host roots for the first live cutover:

- `TARGET_WORKSPACES_ROOT=/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces`
- `TARGET_STORAGE_ROOT=/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/storage`
- `TARGET_MODELS_ROOT=/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/models`

Rationale:

- This keeps `workspaces`, `storage`, and `models` under the same external-drive parent immediately.
- It avoids a same-day rename of the entire existing `LOCAL_CORE_SECRETS_HOST_DIR`.
- It keeps container-visible canonical paths unchanged: `/root/.mindscape/workspaces`, `/root/.mindscape/storage`, `/root/.mindscape/models`.

Required env/config updates for Stage A:

- `.env`
  - add `MINDSCAPE_STORAGE_HOST_DIR=/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/storage`
  - add `MINDSCAPE_MODELS_HOST_DIR=/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/models`
- `docker-compose.yml`
  - keep the existing container destinations
  - add explicit envs in both `backend.environment` and shared `x-runner-environment` for:
    - `WORKSPACE_STORAGE_ROOT=/root/.mindscape/workspaces`
    - `MINDSCAPE_MODEL_ROOT=/root/.mindscape/models`
  - keep `LOCAL_STORAGE_PATH=/root/.mindscape/storage/layer_asset_forge`
  - do **not** treat `MINDSCAPE_RUNTIME_ROOT` as a verified Stage A host-runtime control until the real host-runtime execution path is wired to it
  - if host runtime root movement is required in Stage A, use the verified host env `LAF_HOST_RUNTIME_ROOT` and validate it in the same rollout; otherwise leave host runtime under the existing compatibility path and defer runtime-root migration to Stage B

Why Stage A stops here:

- The current host-runtime/device-node side still assumes `~/.mindscape/models` in multiple places. (E13, E14, E15)
- Do not combine this storage-root fix with a full host-home convention purge in the same rollout.

#### A2. Pre-stage the data while the system remains live

Resolves Problem #1, #3, #4.

Do an initial copy **before** any restart:

```bash
mkdir -p "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/storage"
mkdir -p "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/models"

rsync -aH --info=progress2 "/Users/shock/.mindscape/storage/" "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/storage/"
rsync -aH --info=progress2 "/Users/shock/.mindscape/models/" "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/models/"
```

This phase is safe while live traffic continues because it does not change the active mounts yet.

#### A3. Prepare host-runtime compatibility

Resolves Problem #5.

Before the final cutover, choose one compatibility strategy and keep it for Stage A:

- **Preferred:** keep `~/.mindscape/models` and `~/.mindscape/storage` as **redirected compatibility aliases to the new external-drive roots**, not as independently populated directories, and leave `~/.mindscape/runtimes` unchanged for Stage A.
- Because Device Node `shell_execute` cannot inject per-command env, host-runtime commands should not depend on newly invented envs unless the Device Node process itself is restarted with them. (E21)
- **Acceptable only if verified in the same rollout:** update device-node permissions and restart the host Device Node with explicit `MINDSCAPE_MODEL_ROOT`, `MINDSCAPE_STORAGE_HOST_DIR`, and, if runtime root moves in the same rollout, `LAF_HOST_RUNTIME_ROOT`.

Because `device-node/src/governance/permission-map.ts:74-81` and `device-node/config/permissions.yaml:16-21` currently allow `~/.mindscape/models/**`, Stage A should assume a compatibility path is still needed.

Required clarification:

- "Compatibility path" must mean the old host path resolves to the new canonical root after cutover. Leaving `~/.mindscape/models` or `~/.mindscape/storage` in place as stale standalone directories is not acceptable, because `layer_asset_forge` host-runtime fallbacks still read those locations when env is absent.
- Do **not** rely on symlink-only compatibility for any path that may be accessed through Device Node `filesystem_*` capabilities unless the allowlist also admits the resolved realpath. `device-node/src/capabilities/filesystem.ts` validates `realpath`, so a symlink under `~/.mindscape/...` can still fail permission checks if it points outside the currently allowed tree.
- If Stage A keeps compatibility aliases, add an explicit post-cutover verification that `realpath ~/.mindscape/models` and `realpath ~/.mindscape/storage` resolve to the new external-drive targets, and separately verify whether any Device Node filesystem paths used by host-runtime flows need permission-map expansion.
- If the team cannot provide a verified redirect/allowlist mechanism in the same rollout, Stage A should keep the host-visible canonical paths unchanged and defer any host-runtime path move to a later rollout.

#### A3.5. Align the live installed pack surface before final validation

Resolves Problem #6.

If Stage A includes capability code changes from `mindscape-ai-cloud` that participate in the path contract, include deployment to local-core in the same rollout.

Required rule:

- Treat `mindscape-ai-local-core/backend/app/capabilities/*` as the live runtime source of truth.
- Do not assume that editing cloud repo source alone changes the running local-core pack surface.

Minimum conditional deployment sequence:

1. Package each changed capability pack into `.mindpack`.
2. Install it through `/api/v1/capability-packs/install-from-file`.
3. Verify that the installed local-core copy under `backend/app/capabilities/<pack>/` contains the intended path-contract changes.
4. For host-runtime readiness and host script execution, validate against the installed local-core copy, because the bridge resolves scripts from that surface when `LOCAL_CORE_PROJECT_ROOT` is a host path. (E20)

#### A4. Drain gate for final cutover

Resolves Problem #2, #3, #4.

Do **not** wait for `pending=0`.

Required final cutover gate:

- `SELECT COUNT(*) FROM tasks WHERE status = 'running';` returns `0`
- `SELECT runner_id, profile_code, inflight, heartbeat_at FROM runner_heartbeats WHERE heartbeat_at >= NOW() - interval '2 minutes' ORDER BY heartbeat_at DESC;` shows all active runners at `inflight=0`
- `redis-cli ZCARD mindscape:queue:processing:default_local` returns `0`
- `redis-cli ZCARD mindscape:queue:processing:vision_local` returns `0`
- `redis-cli ZCARD mindscape:queue:processing:browser_local` returns `0`
- after ingress is frozen, the same gate stays green across two consecutive samples (for example 30 seconds apart)

Reason:

- `pending` is durable in Postgres and intentionally rehydrated after restart. (E8, E9)
- `running` plus Redis `processing` are the parts that correspond to active live subprocesses. (E7, E10, E16)
- the heartbeat table retains historical rows, so a plain `ORDER BY heartbeat_at DESC LIMIT 10` query is not a reliable active-runner gate. (E16a)

#### A5. Cutover sequence

Resolves Problem #1, #2, #4, #5, #6.

1. Freeze new ingress.
   - Because no verified global ingress-freeze switch exists, use an operational maintenance window.
   - Recommended approach: temporarily stop or shield user/API entrypoints that create new work, then verify no new `running` tasks appear.
2. Wait until the drain gate in A4 passes, preferably on two consecutive samples after ingress is frozen.
3. Run a final delta copy:

```bash
rsync -aH --delete "/Users/shock/.mindscape/storage/" "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/storage/"
rsync -aH --delete "/Users/shock/.mindscape/models/" "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/models/"
```

4. Apply the `.env` / compose changes.
5. If migration-related pack code changed in `mindscape-ai-cloud`, package + install those packs into local-core and verify the installed copies before reopen. (A3.5)
6. Recreate backend and all runner containers.
   - Backend and runner containers must be recreated because bind-mount sources changed.
7. If the rollout changed host Device Node env/permission policy, restart Device Node and verify that host-runtime tools are reachable again before reopening ingress.
8. Re-run the live validation in Phase 6 before reopening ingress.

#### A6. Reopen service after validation

Resolves Problem #2, #3, #5, #6.

Once smoke checks pass:

- reopen ingress
- let the runner startup backfill repopulate the hot queues from Postgres
- monitor the first minutes of `runner_heartbeats`, Redis processing counts, installed pack availability, and a known `ig` -> `layer_asset_forge` host-runtime flow

### Stage B: Semantic cleanup later

Resolves Problem #1, #5, #6.

After Stage A is stable, finish the architectural cleanup described in `docs/core-architecture/local-runtime-persistence-topology.md:182-214`:

- adopt `LOCAL_CORE_RUNTIME_ROOT_HOST_DIR`
- move from `data/secrets/{workspaces,storage,models}` to `mindscape/{workspaces,storage,models,runtimes,secrets}`
- update the remaining home-path defaults in:
  - `backend/app/services/model_weights_installer.py`
  - `mindscape-ai-cloud/capabilities/layer_asset_forge/services/model_provider.py`
  - `mindscape-ai-cloud/capabilities/layer_asset_forge/model-manifest.yaml`
  - `backend/app/schema/model_manifest_schema.py`
  - `backend/app/capabilities/*` installed copies and their deployment pipeline
  - device-node permission allowlists
  - the host-runtime env contract (`LAF_HOST_RUNTIME_ROOT` vs future unified runtime-root alias)

Do not combine Stage B with Stage A in the same production cutover.

## Phase 5: Citation Audit

Critical citations re-checked immediately before delivering this plan:

- `docker-compose.yml:41-49`, `docker-compose.yml:155-163`
- `mindscape-ai-cloud/capabilities/ig/services/workspace_storage.py:137-145`
- `backend/app/runner/worker.py:93-105`, `backend/app/runner/worker.py:480-486`, `backend/app/runner/worker.py:529-559`
- `backend/app/runner/restart.py:12-13`
- `backend/app/services/model_weights_installer.py:209-220`
- `device-node/src/governance/permission-map.ts:74-81`
- `backend/app/routes/core/capability_packs.py:218-231`
- `backend/app/routes/core/tools/base.py:62-80`
- `backend/app/capabilities/layer_asset_forge/services/host_runtime_bridge.py:693-710`
- `device-node/src/mcp-server.ts:109-126`
- `device-node/src/capabilities/shell.ts:101-166`

The plan above only references insertion points and runtime behavior verified against those locations.

## Phase 6: Validation SOP

### Validation narrative

- Phase 1 established that the runtime split is real and live.
- Phase 2 established that the real operational risk is active subprocess continuity, not the huge pending backlog.
- Phase 4 therefore uses online pre-copy plus a short drain-and-cutover window instead of waiting for all pending work to finish.

### Validation steps

#### V1. Pre-cutover inventory

Run:

```bash
docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "SELECT status, COUNT(*) FROM tasks GROUP BY status ORDER BY status;"
docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "SELECT runner_id, profile_code, inflight, heartbeat_at FROM runner_heartbeats WHERE heartbeat_at >= NOW() - interval '2 minutes' ORDER BY heartbeat_at DESC;"
docker exec mindscape-ai-local-core-redis redis-cli ZCARD mindscape:queue:processing:default_local
docker exec mindscape-ai-local-core-redis redis-cli ZCARD mindscape:queue:processing:vision_local
docker exec mindscape-ai-local-core-redis redis-cli ZCARD mindscape:queue:processing:browser_local
```

Pass:

- You know exactly whether live work is still running.

Fail:

- You do not have a reliable count for `running`, `inflight`, and Redis processing membership.

#### V2. Final drain gate

Run the same commands until:

- `tasks.status='running' = 0`
- all active runner heartbeat rows show `inflight=0`
- all processing ZSET counts are `0`
- after ingress freeze, the gate remains green across two consecutive samples

Pass:

- No active live subprocess remains to be interrupted.

Fail:

- Any of the above counters are still non-zero, or fresh active rows keep reappearing.

#### V3. Installed-pack verification for any shipped capability changes

Run:

```bash
rg -n "WORKSPACE_STORAGE_ROOT|MINDSCAPE_MODEL_ROOT|LAF_HOST_RUNTIME_ROOT|MINDSCAPE_STORAGE_HOST_DIR" \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/ig \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/layer_asset_forge \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/web_generation

rg -n "~/.mindscape/(workspaces|models|storage)" \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/ig \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/layer_asset_forge \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/web_generation
```

Pass:

- If the rollout included pack code changes, the installed local-core copy reflects the intended path-contract updates.
- Any intentionally retained `~/.mindscape/*` fallback is explicitly documented as a temporary compatibility alias and not an accidental stale hardcode.
- Validation is being performed against the surface that local-core actually executes.

Fail:

- Only the cloud repo changed, but the installed local-core pack copy did not.
- Installed-pack files still contain undeclared `~/.mindscape/*` fallbacks that would bypass the new canonical roots.

Stronger option for changed files:

- For every file modified in the rollout, diff the installed local-core copy against the reviewed source change set instead of relying only on broad grep. This is preferred for `ig/services/workspace_storage.py`, `web_generation/api/dependencies.py`, and `layer_asset_forge/services/model_provider.py`, where a leftover fallback can survive a simple env-name grep.

#### V4. Mount/env verification after recreate

Run:

```bash
docker inspect mindscape-ai-local-core-backend --format '{{json .Mounts}}'
docker inspect mindscape-ai-local-core-backend --format '{{json .Config.Env}}'
docker inspect mindscape-ai-local-core-runner-default --format '{{json .Mounts}}'
docker inspect mindscape-ai-local-core-runner-default --format '{{json .Config.Env}}'
docker inspect mindscape-ai-local-core-runner-browser --format '{{json .Mounts}}'
docker inspect mindscape-ai-local-core-runner-browser --format '{{json .Config.Env}}'
docker inspect mindscape-ai-local-core-runner-vision --format '{{json .Mounts}}'
docker inspect mindscape-ai-local-core-runner-vision --format '{{json .Config.Env}}'
```

Pass:

- backend and every live runner profile mount `storage` and `models` from the new external-drive roots
- `WORKSPACE_STORAGE_ROOT` is present anywhere it is expected to be consumed
- `LOCAL_STORAGE_PATH` and `MINDSCAPE_MODEL_ROOT` resolve to container-visible canonical paths
- if the rollout intentionally changed the host runtime root, the corresponding verified env (`LAF_HOST_RUNTIME_ROOT`) has been handled in the host runtime/device-node layer, not just in docs

Fail:

- mounts still point to `/Users/shock/.mindscape/{storage,models}`
- `WORKSPACE_STORAGE_ROOT` is still unset where required
- browser or vision runners still differ from the verified backend/default runner contract

#### V5. Functional smoke for workspace refs and storage-key artifacts

Run:

```bash
curl -sS http://127.0.0.1:8000/api/v1/capabilities/layer_asset_forge/runtime/plan | jq .
```

Then re-run one live smoke on:

- a `storage_key` path
- an `ig` `reference_id + workspace_id` path

Pass:

- `/api/v1/capabilities/layer_asset_forge/runtime/plan` returns a payload built through `runtime_install -> host_runtime_bridge.probe -> Device Node shell_execute`, so the observed readiness reflects the live Device Node execution path
- host-runtime pose extraction completes for both modes
- resolved host paths point at the intended storage/model roots or the explicitly retained compatibility aliases
- the live execution path uses the installed local-core pack surface, not only the cloud repo test surface

Fail:

- the API probe disagrees with an operator-shell direct script run, indicating Device Node env drift or permission drift
- host runtime cannot resolve model or storage paths after the mount change
- host runtime still resolves through an unintended stale installed pack copy or stale host alias

Fallback only if the API probe is unavailable:

- Inspect the live Device Node process env first, then run `check_laf_host_runtime_readiness.py` from the installed local-core path on the host and treat the result as advisory only. Do not accept a direct operator-shell script run as the sole green signal when the real production path is `shell_execute`.

### Pass/fail mapping to problems

- Problem #1 passes when mounts and envs are unified and verified.
- Problem #2 passes when cutover happens only after `running/inflight/processing=0`.
- Problem #3 passes when pending backlog remains durable and is rehydrated after restart.
- Problem #4 passes when no late writes land during final sync because ingress is frozen.
- Problem #5 passes when host-runtime/model access still works after cutover.
- Problem #6 passes when any shipped pack changes are installed into local-core and validated against `backend/app/capabilities/*`.
- Problem #7 passes when the migration checklist explicitly accounts for out-of-scope artifacts such as `/tmp/mindscape-workspace`, instead of silently assuming they moved.

## Phase 7: Evaluation & Automated Testing SOP

### T1. Config contract regression test

Protects Problem #1 and #5.

Add a configuration-level test that renders the effective backend and runner environments/mounts and asserts:

- `WORKSPACE_STORAGE_ROOT == /root/.mindscape/workspaces`
- `LOCAL_STORAGE_PATH` is under `/root/.mindscape/storage/`
- `MINDSCAPE_MODEL_ROOT == /root/.mindscape/models`
- if `MINDSCAPE_STORAGE_HOST_DIR` / `MINDSCAPE_MODELS_HOST_DIR` are set, they are not left empty
- backend, `runner-default`, `runner-browser`, and `runner-vision` all resolve the same intended storage/model bind sources

Expected output:

- test fails if the compose/env policy drifts back to implicit `HOME` defaults.

### T2. Runtime persistence readiness smoke

Protects Problem #2, #3, and #4.

Add a script or CI-friendly smoke that:

1. queries `tasks` grouped by status
2. queries `runner_heartbeats` with a freshness filter
3. queries Redis `processing` counts
4. emits a single pass/fail verdict:
   - pass only if `running=0`, all active `inflight=0`, and processing ZSETs are `0`
5. optionally repeats the gate twice after an ingress freeze to reduce false-green race windows

Expected output:

- this becomes the mandatory gate before any future mount or runtime-root migration.

### T3. Host-runtime path smoke

Protects Problem #5.

Exact test cases:

1. **Live API probe smoke**
   - Input: `GET /api/v1/capabilities/layer_asset_forge/runtime/plan`
   - Setup: local-core backend and Device Node are running with the rollout's real env/mount contract
   - Expected: the returned readiness payload reflects the live Device Node `shell_execute` path, not only an operator-shell direct script run
2. **Storage-key path smoke**
   - Input: one known `storage_key`
   - Setup: backend env points at the migrated storage root
   - Expected: host-runtime command resolves the image path under the migrated storage root and completes
3. **Workspace ref smoke**
   - Input: one known `workspace_id + reference_id`
   - Setup: `WORKSPACE_STORAGE_ROOT` is explicit and the ref exists under the migrated workspace root
   - Expected: `resolve_ref_to_local_path` returns a file under `/root/.mindscape/workspaces/...` and pose extraction completes
4. **Model lookup smoke**
   - Input: one known reviewed LAF model
   - Setup: migrated model root populated
   - Expected: the installed local-core readiness surface reports the model present and usable, and any direct script run is treated as secondary evidence unless it matches the live API probe
5. **Compatibility-or-env gate**
   - Input: host runtime process environment or compatibility aliases
   - Setup: choose either retained `~/.mindscape/*` compatibility paths or explicit device-node env propagation
   - Expected: host runtime still resolves models/storage without relying on undocumented per-command env injection

### T4. Deferred Stage B audit

Protects Problem #5 and #6 long-term.

Add a repo audit test that fails if new code introduces fresh hardcoded `~/.mindscape/models` or `~/.mindscape/workspaces` defaults outside approved compatibility layers, or if installed-pack/runtime surfaces drift from the intended contract.

Suggested grep scope:

```bash
rg -n "~/.mindscape/models|~/.mindscape/workspaces|~/.mindscape/storage|~/.mindscape/runtimes|Path.home\\(\\) / \".mindscape\"|LAF_HOST_RUNTIME_ROOT|MINDSCAPE_RUNTIME_ROOT" backend backend/app/capabilities capabilities services scripts device-node
```

Expected output:

- only approved compatibility shims remain
- new direct assumptions are blocked from landing silently

### T5. Installed-pack parity gate

Protects Problem #6.

Exact test cases:

1. **Pack deployment parity**
   - Input: each changed cloud pack that participates in the path contract
   - Setup: package into `.mindpack` and install into a local-core instance
   - Expected: the installed copy under `backend/app/capabilities/<pack>/` contains the expected path/env contract changes
2. **Installed-surface smoke**
   - Input: one representative live path-resolution flow per changed pack
   - Setup: execute it against local-core after install, not only against cloud repo tests
   - Expected: runtime behavior matches the installed pack copy

Expected output:

- rollout fails if cloud repo code changes were prepared but never propagated to the live installed local-core pack surface

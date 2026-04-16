# Local Runtime Persistence Topology

Status: proposed convergence plan
Last updated: 2026-04-14
Owner surface: `mindscape-ai-local-core`

## Purpose

This document is the canonical reference for how Local-Core maps persistent host
directories into the runtime container.

It exists because the current development topology is functional but not
semantically clean: different subtrees under `/root/.mindscape` come from
different host roots, and the implicit defaults in code do not make that
obvious.

## Scope

This document covers:

- local runtime host directories
- Docker bind mounts into the Local-Core backend container
- the canonical meaning of `workspaces`, `storage`, `models`, and `runtimes`
- the environment-variable policy that should own those mappings

This document does not define:

- pack-level manifest contracts
- cross-pack runtime aliases
- cloud deployment topology

## Current Actual Topology

As of the current dev runtime, the backend container uses these effective
mounts:

| Container path | Current host source | Meaning |
| --- | --- | --- |
| `/root/.mindscape` | `${LOCAL_CORE_SECRETS_HOST_DIR}` | base runtime state, keys, and any subtree not shadowed by a more specific mount |
| `/root/.mindscape/workspaces` | inherited from `${LOCAL_CORE_SECRETS_HOST_DIR}` | workspace-scoped capability data |
| `/root/.mindscape/storage` | `${MINDSCAPE_STORAGE_HOST_DIR}` | storage-key artifacts and generated assets |
| `/root/.mindscape/models` | `${MINDSCAPE_MODELS_HOST_DIR}` | shared model weights |
| `/app/data` | `${LOCAL_CORE_DATA_HOST_DIR}` | app runtime data outside `.mindscape` |
| `/app/logs` | `${LOCAL_CORE_LOGS_HOST_DIR}` | logs |

In the observed live setup, that means:

| Runtime concern | Current host root |
| --- | --- |
| workspaces | `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces` |
| storage | `/Users/shock/.mindscape/storage` |
| models | `/Users/shock/.mindscape/models` |
| logs | `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/logs` |
| app data | `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data` |

## Why The Current State Is Confusing

`/root/.mindscape` looks like a single logical tree, but it is not.

- `workspaces` currently comes from the secrets/runtime volume.
- `storage` currently comes from a direct host `~/.mindscape/storage` bind mount.
- `models` currently comes from a direct host `~/.mindscape/models` bind mount.

So a path under host `~/.mindscape/workspaces` is not automatically visible to
the live backend, while sibling paths under host `~/.mindscape/storage` and
`~/.mindscape/models` are.

That mismatch is the root cause behind "I can see this ref on the host, but the
live backend cannot resolve it" style failures.

## Canonical Data Taxonomy

### 1. Workspace-scoped capability data

Container root:

```text
/root/.mindscape/workspaces/{workspace_id}/{pack_code}/...
```

Examples:

- IG references
- workspace-local pack caches
- workspace-local outputs that are part of the capability data model

This data is owned by the workspace/capability boundary, not by artifact
storage.

### 2. Storage-key artifact store

Container root:

```text
/root/.mindscape/storage/{pack_code}/{tenant_id}/...
```

Examples:

- generated images
- exported manifests
- pose signals
- any asset addressed by `storage_key`

This data is addressed through capability storage APIs and is not the same thing
as workspace-local pack data.

### 3. Shared model cache

Container root:

```text
/root/.mindscape/models/{role_or_pack}/{model_id}/...
```

Examples:

- pack model weights
- shared inference checkpoints

This data is runtime-level and should be reusable across workspaces.

### 4. Runtime environments and tooling

Container root:

```text
/root/.mindscape/runtimes/{pack_code}/...
```

Examples:

- pack-specific venvs
- helper binaries
- runtime state files

### 5. Secrets and identity material

Container root:

```text
/root/.mindscape/<keys, tokens, config>
```

This remains distinct from workspace data even if it shares the same top-level
tree.

## Convergence Policy

The preferred policy is:

1. Define one runtime host root.
2. Explicitly derive all persistent sub-roots from that runtime host root.
3. Stop relying on implicit `Path.home() / ".mindscape"` defaults in container
   runtime policy.
4. Keep pack-level segmentation inside the canonical subtrees, not in the Docker
   mount layout.

### Recommended top-level host root

```text
LOCAL_CORE_RUNTIME_ROOT_HOST_DIR=/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime
```

### Recommended persistent subtree layout

```text
${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/
├── app-data/
├── logs/
└── mindscape/
    ├── workspaces/
    ├── storage/
    ├── models/
    ├── runtimes/
    ├── cache/
    └── secrets/
```

### Recommended container mapping

| Container path | Recommended host source |
| --- | --- |
| `/root/.mindscape/workspaces` | `${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/mindscape/workspaces` |
| `/root/.mindscape/storage` | `${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/mindscape/storage` |
| `/root/.mindscape/models` | `${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/mindscape/models` |
| `/root/.mindscape/runtimes` | `${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/mindscape/runtimes` |
| `/root/.mindscape/secrets` | `${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/mindscape/secrets` |
| `/app/data` | `${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/app-data` |
| `/app/logs` | `${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/logs` |

## Environment Variable Policy

The container should not infer persistence roots from `HOME` unless no runtime
policy has been configured at all.

The preferred policy is:

| Variable | Meaning |
| --- | --- |
| `LOCAL_CORE_RUNTIME_ROOT_HOST_DIR` | single host root for Local-Core runtime persistence |
| `WORKSPACE_STORAGE_ROOT` | explicit container-visible root for workspace data |
| `LOCAL_STORAGE_PATH` | explicit container-visible root for capability storage APIs |
| `MINDSCAPE_MODEL_ROOT` | explicit container-visible root for shared models |
| `MINDSCAPE_RUNTIME_ROOT` | explicit container-visible root for pack runtimes |

Recommended derived values inside the container:

```text
WORKSPACE_STORAGE_ROOT=/root/.mindscape/workspaces
LOCAL_STORAGE_PATH=/root/.mindscape/storage/layer_asset_forge
MINDSCAPE_MODEL_ROOT=/root/.mindscape/models
MINDSCAPE_RUNTIME_ROOT=/root/.mindscape/runtimes
```

Recommended derived values on the host:

```text
LOCAL_CORE_RUNTIME_ROOT_HOST_DIR=/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime
LOCAL_CORE_APP_DATA_HOST_DIR=${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/app-data
LOCAL_CORE_LOGS_HOST_DIR=${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/logs
LOCAL_CORE_MINDSCAPE_HOST_DIR=${LOCAL_CORE_RUNTIME_ROOT_HOST_DIR}/mindscape
LOCAL_CORE_WORKSPACES_HOST_DIR=${LOCAL_CORE_MINDSCAPE_HOST_DIR}/workspaces
LOCAL_CORE_STORAGE_HOST_DIR=${LOCAL_CORE_MINDSCAPE_HOST_DIR}/storage
LOCAL_CORE_MODELS_HOST_DIR=${LOCAL_CORE_MINDSCAPE_HOST_DIR}/models
LOCAL_CORE_RUNTIMES_HOST_DIR=${LOCAL_CORE_MINDSCAPE_HOST_DIR}/runtimes
LOCAL_CORE_SECRETS_HOST_DIR=${LOCAL_CORE_MINDSCAPE_HOST_DIR}/secrets
```

## Repository Documentation Policy

This document is the architecture source of truth for local persistence mapping.

Other docs should:

- link here instead of re-describing the topology in detail
- only describe user-facing setup consequences
- avoid implying that host `~/.mindscape/*` is always the runtime source of truth

## Required Follow-up Implementation Work

This document does not itself change runtime behavior. The follow-up work should
be tracked separately:

1. Refactor `docker-compose.yml` to derive mounts from a single runtime root.
2. Set `WORKSPACE_STORAGE_ROOT` explicitly in compose.
3. Decide whether legacy direct host `~/.mindscape/models` and
   `~/.mindscape/storage` mounts remain supported as compatibility overrides.
4. Audit pack code that hardcodes `~/.mindscape/models` or host-path assumptions
   and move those call sites to explicit runtime root envs.
5. Provide a migration script or operator playbook for moving existing host data
   into the canonical runtime root.

## Decision Summary

The intended steady state is not "some `.mindscape` subtrees come from one host
root and others from another". The intended steady state is:

- one runtime host root
- explicit subdirectory taxonomy
- explicit container env roots
- pack-level segregation inside those roots

Anything else should be treated as transitional compatibility, not as the
architecture.

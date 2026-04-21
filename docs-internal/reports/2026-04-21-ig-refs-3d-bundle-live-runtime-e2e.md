# IG Refs -> 3D Asset Bundle Live Runtime E2E

Date: 2026-04-21

## Scope

This report answers one narrow question with live runtime evidence only:

- Can the currently deployed `ig` pack expose a real IG reference's 3D bundle
  through the live refs detail API?
- Can the currently deployed local-core runtime generate a new 3D bundle from
  that same live reference right now?

## Deployment Baseline

Cloud repo state used for this e2e:

- `mindscape-ai-cloud` on `master`
- deployed IG source commit: `17c2890`
- later full-worktree persistence commit on `master`: `43e42fd`

Local-core state used for this e2e:

- `mindscape-ai-local-core` on `master`
- current local-core persistence commit: `fcbe7b2`

Install / reload evidence from live `backend-control` logs:

- `POST /api/v1/capability-packs/install-from-file HTTP/1.1" 200 OK`
- `Reloaded capability registry for ig`
- `Loaded 122 playbooks from ig`
- `Playbook ig_analyze_pinned_reference validated successfully`
- `Playbook ig_batch_pin_references validated successfully`

Container health evidence at the time of validation:

- `mindscape-ai-local-core-backend Up ... (healthy)`
- `mindscape-ai-local-core-backend-control Up ... (healthy)`

## Test Target

Primary live reference used for positive-path validation:

- workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- reference: `ref_2bcb6ece`
- account / shortcode: `@jc6jf4.__ / DK9XiIZyUFx`

Negative control references used to prove the API is not blindly fabricating 3D:

- `ref_e6cf189f`
- `ref_d52eaaf4`

## Truth Table

| Check | Result | Evidence |
|---|---|---|
| Latest IG pack deployed into local-core | TRUE | Install returned `200 OK`; control plane reloaded `ig`; `122` playbooks loaded |
| Live refs detail can return a real 3D bundle | TRUE | `ref_2bcb6ece` detail returns populated `spatial_3d_assets` |
| Returned 3D bundle is a real candidate bundle, not an empty shell | TRUE | API returns `single_image_bootstrap`, `promotion_state=candidate`, downloads for `Receipt JSON`, `Person Model`, `Person Mesh` |
| Runtime metadata file for the same ref contains the 3D bundle keys | TRUE | live JSON contains `bootstrap_id=sib_dk9x_20260421`, `person_model_ref`, `person_mesh_ref`, `single_image_bootstrap_receipt_ref` |
| Every analyzed ref has a 3D bundle | FALSE | `ref_e6cf189f` and `ref_d52eaaf4` are `COMPLETED` but `spatial_3d_assets=null` |
| Current local-core can re-run new 3D generation from the same ref | FALSE | direct `bb_generate_single_image_modeled_mesh_preview(...)` raises `RuntimeError: blender_bridge_runtime_not_ready` |

## Live Evidence

### 1. Positive-path live detail response

Command:

```bash
curl -sS \
  'http://localhost:8200/api/v1/ig/references/ref_2bcb6ece/detail?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69' \
  | jq '{
      reference_id,
      analysis_status,
      analysis_phase,
      bundle_family: .spatial_3d_assets.artifact_family,
      promotion_state: .spatial_3d_assets.promotion_state,
      backend: .spatial_3d_assets.backend,
      downloads: [.spatial_3d_assets.downloads[].label],
      candidate_labels: [.spatial_3d_assets.candidates[].label],
      candidate_actions: [.spatial_3d_assets.candidates[].available_actions[]]
    }'
```

Observed result:

```json
{
  "reference_id": "ref_2bcb6ece",
  "analysis_status": "COMPLETED",
  "analysis_phase": "completed",
  "bundle_family": "single_image_bootstrap",
  "promotion_state": "candidate",
  "backend": "single_image_modeled_mesh_composition_backend",
  "downloads": [
    "Receipt JSON",
    "Person Model",
    "Person Mesh"
  ],
  "candidate_labels": [
    "Person Model",
    "Person Mesh"
  ],
  "candidate_actions": [
    "attach_character_card",
    "queue_preview",
    "attach_character_card",
    "queue_preview"
  ]
}
```

Interpretation:

- The live IG refs detail API is already surfacing a real 3D candidate bundle
  for this ref.
- The returned payload is actionable, not just decorative metadata.

### 2. Positive-path live runtime metadata file

Command:

```bash
jq '{
  reference_id,
  bootstrap_id,
  promotion_state,
  backend,
  source_family,
  person_model_key: .person_model_ref.storage_key,
  person_mesh_key: .person_mesh_ref.storage_key,
  receipt_key: .single_image_bootstrap_receipt_ref.storage_key
}' \
'/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@jc6jf4.__/DK9XiIZyUFx.json'
```

Observed result:

```json
{
  "reference_id": "ref_2bcb6ece",
  "bootstrap_id": "sib_dk9x_20260421",
  "promotion_state": "candidate",
  "backend": "single_image_modeled_mesh_composition_backend",
  "source_family": "ig_single_image_reference",
  "person_model_key": "blender_bridge/single_image_bootstrap/sib_dk9x_20260421/person_model.glb",
  "person_mesh_key": "blender_bridge/single_image_bootstrap/sib_dk9x_20260421/person_mesh.glb",
  "receipt_key": "blender_bridge/single_image_bootstrap/sib_dk9x_20260421/single_image_bootstrap_receipt.json"
}
```

Interpretation:

- The API response is backed by real runtime metadata for the same live ref.
- The candidate bundle has concrete storage keys for receipt and person assets.

### 3. Negative controls

Commands:

```bash
curl -sS \
  'http://localhost:8200/api/v1/ig/references/ref_e6cf189f/detail?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69' \
  | jq '{reference_id, analysis_status, analysis_phase, spatial_3d_assets}'

curl -sS \
  'http://localhost:8200/api/v1/ig/references/ref_d52eaaf4/detail?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69' \
  | jq '{reference_id, analysis_status, analysis_phase, spatial_3d_assets}'
```

Observed results:

```json
{
  "reference_id": "ref_e6cf189f",
  "analysis_status": "COMPLETED",
  "analysis_phase": "completed",
  "spatial_3d_assets": null
}
```

```json
{
  "reference_id": "ref_d52eaaf4",
  "analysis_status": "COMPLETED",
  "analysis_phase": "completed",
  "spatial_3d_assets": null
}
```

Interpretation:

- The live API is not inventing 3D bundles for every analyzed ref.
- 3D candidate presence is ref-specific and data-driven.

### 4. Current local-core generation readiness

Command:

```bash
/usr/local/bin/docker exec mindscape-ai-local-core-backend python3 -c \
"from app.capabilities.blender_bridge.services.runtime_readiness import BlenderBridgeReadinessService; import json; state=BlenderBridgeReadinessService().get_state(); print(json.dumps({'ready': state['ready'], 'status': state['status'], 'missing': state['missing'], 'scene_profile_ready': state['profiles']['scene_profile_mesh_runtime']['ready'], 'person_profile_ready': state['profiles']['person_profile_human_mesh_runtime']['ready'], 'object_profile_ready': state['profiles']['object_mesh_aux_profile']['ready']}, indent=2))"
```

Observed result:

```json
{
  "ready": false,
  "status": "not_ready",
  "missing": [
    "blender_executable_path"
  ],
  "scene_profile_ready": false,
  "person_profile_ready": false,
  "object_profile_ready": false
}
```

Interpretation:

- The currently deployed local-core runtime is not configured to generate a new
  3D bundle right now.
- This is a runtime readiness blocker, not an IG refs API blocker.

### 5. Direct generation attempt against the same live ref

Command:

```bash
/usr/local/bin/docker exec -i mindscape-ai-local-core-backend python3 - <<'PY'
import asyncio
from app.capabilities.blender_bridge.tools.bb_generate_single_image_modeled_mesh_preview import bb_generate_single_image_modeled_mesh_preview

async def main():
    try:
        await bb_generate_single_image_modeled_mesh_preview(
            reference_id='ref_2bcb6ece',
            workspace_id='bac7ce63-e768-454d-96f3-3a00e8e1df69',
            scene_id='ig_ref_dk9x_e2e',
            require_ready=True,
            materialize_outputs=True,
            execution_mode='inline',
        )
    except Exception as exc:
        print(type(exc).__name__)
        print(str(exc))

asyncio.run(main())
PY
```

Observed result:

```text
RuntimeError
blender_bridge_runtime_not_ready
```

Interpretation:

- Re-running new 3D generation from the current local-core deployment fails at
  the runtime gate exactly where readiness said it would.

## Verdict

### Pass

`IG refs -> live 3D asset bundle readback` is working.

The currently deployed IG pack can already surface a real candidate 3D bundle
for at least one live IG ref (`ref_2bcb6ece`) with:

- candidate bundle family
- candidate status
- receipt / person model / person mesh downloads
- character candidate rows
- actionable candidate actions

### Fail

`IG refs -> generate a new 3D asset bundle now` is not currently working on
this local-core runtime.

The live blocker is:

- `blender_bridge_runtime_not_ready`

with readiness showing:

- missing `blender_executable_path`
- scene/person/object modeled runtime profiles all `not_ready`

## Bottom Line

If the question is:

- "Can the current deployed IG detail read and expose an existing live 3D
  bundle?" -> **YES**
- "Can the current deployed local-core regenerate a new 3D bundle from a live
  IG ref right now?" -> **NO**

The read path is live. The generate path is still runtime-blocked.

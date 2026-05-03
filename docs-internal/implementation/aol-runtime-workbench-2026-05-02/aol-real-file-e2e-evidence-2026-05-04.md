# AOL Real File E2E Evidence - 2026-05-04

## Final Verdict

Fresh post-restart closure command `cmd_aol_real_e2e_files_20260504_021_tasklineage` is the current acceptance record for the original AOL -> MeetingEngine -> Performance Direction storyboard E2E.

Verified:

- Command id: `cmd_aol_real_e2e_files_20260504_021_tasklineage`
- TaskIR id: `task_f385ff20d3364399`
- Downstream execution id: `7ba39e58-e19f-4113-b8db-5547558e26bd`
- Playbook: `performance_direction/pd_storyboard_gen`
- Meeting session id / artifact thread id: `0f2463d0-2f22-4016-9b5d-cb3b389eb8d1`
- Storyboard id: `sb_a75480dadd93`
- Direction session id: `ds_f4ae71893782`
- Source refs preserved: `codex_aol_e2e_ref_a_20260503`, `codex_aol_e2e_ref_b_20260503`
- Command response status: `status=completed`, `dispatch_result.meeting_orchestration.status=completed`, `artifact_landing_status=landed`
- Artifact DB ids: `42e2c149-3c1e-42eb-aa58-d472437a55af`, `18420a74-86c5-4853-923a-1753c8ca8bb9`, `632f963a-a209-4a7e-b478-da165f2da2a2`
- Artifact files: contact-sheet SVG, proposal Markdown, and storyboard manifest JSON under `/app/data/sandboxes/.../current/artifacts/pd_storyboard_gen/7ba39e58-e19f-4113-b8db-5547558e26bd/`
- DB lineage: all three artifact rows have `thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1` and `task_id=task_f385ff20d3364399`
- Pack-owned evidence: all three artifact rows include `metadata.acceptance_evidence`, `metadata.pd_storyboard_evidence`, and `metadata.provenance.eval_summary.passed=true`

Content acceptance check:

```json
{
  "storyboard_id": "sb_a75480dadd93",
  "status": "draft",
  "scene_count": 9,
  "total_duration_sec": 90,
  "all_have_frames": true,
  "all_need_review": true,
  "all_have_discussion_prompt": true,
  "all_have_decision_items": true,
  "all_have_review_candidates": true,
  "render_profile": "pd_vertical_reels_storyboard"
}
```

This closes the two hard E2E lanes for the tested fixture:

- AOL object refs enter `route_meeting_orchestration`, MeetingEngine produces TaskIR, and downstream PD playbook dispatch lands successfully.
- The resulting storyboard/proposal/contact-sheet artifacts are real files and artifacts table rows, queryable by the meeting thread id.

The contact sheet is an SVG storyboard image artifact, not a final rendered video or raster production frame. Human review is represented as per-scene `meeting_discussion_prompt`, `decision_items`, `review_candidates`, and `approval_state=needs_review`; a live human discussion session resolving those decisions is outside this run.

## Historical `_014` Verdict (Superseded)

The `_014` record below is retained as a rejection baseline. It is not the current acceptance record for the original `90s reels` storyboard and storyboard image request.

Verified AOL -> MeetingEngine -> playbook dispatch -> proposal/manifest real-file artifact landing:

- Command id: `cmd_aol_real_e2e_files_20260504_014`
- TaskIR id: `task_fb5bd9966bc544f9`
- Execution id: `fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218`
- Playbook: `performance_direction/pd_storyboard_gen`
- Meeting session id carried in output: `0f2463d0-2f22-4016-9b5d-cb3b389eb8d1`
- Direction session id: `ds_a1d6615e5b59`
- Storyboard id: `sb_0eefa25cb814`
- Source refs preserved: `codex_aol_e2e_ref_a_20260503`, `codex_aol_e2e_ref_b_20260503`
- Command response status: `status=completed`, `dispatch_result.meeting_orchestration.status=completed`, `artifact_landing_status=landed`
- Command response artifact files: proposal markdown and manifest JSON both returned under `artifact_file_paths`

Rejected as original product deliverable evidence:

- `_014` does not satisfy `90s reels`: manifest content has `scene_count=1` and `total_duration_sec=5.0`.
- `_014` does not satisfy storyboard image production: the artifact directory contains only one JSON manifest and one Markdown proposal; no `.png`, `.jpg`, `.jpeg`, `.webp`, or `.svg` storyboard frame/image files were present.
- `_014` does not prove per-scene PD discussion/review: manifest content has `scene_manifest={}`, `render_profile=null`, `object_assets=[]`, `review_candidates=[]`, `approval_state=""`, and `clip_refs=[]`.

Not counted as successful bridge E2E:

- `cmd_aol_real_e2e_files_20260504_002` timed out at MeetingEngine orchestration and is not evidence of artifact landing.
- `cmd_aol_real_e2e_files_20260504_009` / `_010` / `_011` / `_013` were diagnostic runs only; `_014` is the first fresh command response in this sequence that returned both output file paths and `artifact_landing_status=landed`.
- Wrapper/result directories under `backend/data/workspaces/.../artifacts/<execution_id>` are not counted as output artifact files unless backed by concrete output materialization files.

## Real Files

Host path:

```text
/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/277c2b2d-8adc-493d-b991-dda859f7cc95/current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218/pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json
```

```text
/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/277c2b2d-8adc-493d-b991-dda859f7cc95/current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218/pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md
```

Container path recorded by artifact metadata:

```text
/app/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/277c2b2d-8adc-493d-b991-dda859f7cc95/current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218/pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json
```

```text
/app/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/277c2b2d-8adc-493d-b991-dda859f7cc95/current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218/pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md
```

## Filesystem Evidence

Command:

```bash
ls -la '/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/277c2b2d-8adc-493d-b991-dda859f7cc95/current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218'
```

Observed:

```text
pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json  7412 bytes
pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md      8800 bytes
```

Command:

```bash
file '<manifest-host-path>' '<proposal-host-path>'
```

Observed:

```text
pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json: JSON data
pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md: ASCII text, with very long lines (8800), with no line terminators
```

## Command Response Evidence

Command:

```bash
curl -sS -m 660 --fail-with-body -H 'Content-Type: application/json' --data-binary @/private/tmp/aol_e2e_014.json http://127.0.0.1:8220/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/meetings/0f2463d0-2f22-4016-9b5d-cb3b389eb8d1/commands
```

Observed key fields:

```json
{
  "command_id": "cmd_aol_real_e2e_files_20260504_014",
  "status": "completed",
  "task_ir_id": "task_fb5bd9966bc544f9",
  "dispatch_status": "completed",
  "execution_id": "fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218",
  "artifact_ids": [
    "6772eb0e-4dfa-43c9-8e71-c1a171a61bee",
    "d82a59c1-5368-49bd-a579-12c33544675f"
  ],
  "artifact_db_ids": [
    "6772eb0e-4dfa-43c9-8e71-c1a171a61bee",
    "d82a59c1-5368-49bd-a579-12c33544675f"
  ],
  "artifact_file_paths": [
    "/app/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/277c2b2d-8adc-493d-b991-dda859f7cc95/current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218/pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md",
    "/app/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/277c2b2d-8adc-493d-b991-dda859f7cc95/current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218/pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json"
  ],
  "artifact_landing_status": "landed"
}
```

## Content Evidence

Command:

```bash
jq '{storyboard_id:.storyboard_id, workspace_id:.workspace_id, scene_count:(.scenes|length), refs:(.scenes[0].reference_ids // .global_settings.aol_reference_ids // []), command_id:.global_settings.addressable_object_layer.command_id}' '<manifest-host-path>'
```

Observed:

```json
{
  "storyboard_id": "sb_0eefa25cb814",
  "workspace_id": "bac7ce63-e768-454d-96f3-3a00e8e1df69",
  "scene_count": 1,
  "refs": [
    "codex_aol_e2e_ref_a_20260503",
    "codex_aol_e2e_ref_b_20260503"
  ],
  "command_id": "cmd_aol_real_e2e_files_20260504_014"
}
```

Product acceptance rejection check:

```bash
jq '{storyboard_id, status, scene_count:(.scenes|length), total_duration_sec:([.scenes[]?.duration_sec] | add), first_scene:{scene_id:.scenes[0].scene_id, duration_sec:.scenes[0].duration_sec, scene_manifest:.scenes[0].scene_manifest, render_profile:.render_profile, object_assets:.scenes[0].object_assets, review_candidates:.scenes[0].review_candidates, approval_state:.scenes[0].approval_state, clip_refs:.scenes[0].clip_refs}}' '<manifest-host-path>'
```

Observed:

```json
{
  "storyboard_id": "sb_0eefa25cb814",
  "status": "draft",
  "scene_count": 1,
  "total_duration_sec": 5.0,
  "first_scene": {
    "scene_id": "sc01",
    "duration_sec": 5.0,
    "scene_manifest": {},
    "render_profile": null,
    "object_assets": [],
    "review_candidates": [],
    "approval_state": "",
    "clip_refs": []
  }
}
```

Storyboard image artifact check:

```bash
find '<artifact-dir>' -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.svg' \) -print
```

Observed: no output.

Artifact directory file list:

```bash
find '<artifact-dir>' -maxdepth 1 -type f -print
```

Observed:

```text
<artifact-dir>/pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json
<artifact-dir>/pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md
```

Command:

```bash
rg -n 'codex_aol_e2e_ref_a_20260503|codex_aol_e2e_ref_b_20260503|Performance Direction Storyboard Proposal|storyboard_id|cmd_aol_real_e2e_files_20260504_014' '<artifact-dir>'
```

Observed:

- Markdown proposal contains `# Performance Direction Storyboard Proposal`.
- Markdown proposal contains `session_id: ds_a1d6615e5b59`.
- Markdown proposal contains both selected AOL source refs.
- JSON manifest contains `storyboard_id: sb_0eefa25cb814`.
- JSON manifest contains `command_id: cmd_aol_real_e2e_files_20260504_014`.
- JSON manifest contains both selected AOL source refs in scene references and global settings.

## Database Evidence

Command:

```bash
docker exec mindscape-ai-local-core-backend python -c "from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore; import json; store=PostgresArtifactsStore(); arts=store.list_by_execution_id('fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218'); print(json.dumps([{ 'id':a.id, 'type':getattr(a.artifact_type,'value',a.artifact_type), 'title':a.title, 'storage_ref':a.storage_ref, 'actual_file_path':(a.metadata or {}).get('actual_file_path') } for a in arts], indent=2, default=str))"
```

Observed artifact rows:

| id | artifact_type | title | actual_file_path |
|---|---|---|---|
| `6772eb0e-4dfa-43c9-8e71-c1a171a61bee` | `draft` | `PD Storyboard Proposal - fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218` | `/app/data/sandboxes/.../pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md` |
| `d82a59c1-5368-49bd-a579-12c33544675f` | `data` | `PD Storyboard Manifest - fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218` | `/app/data/sandboxes/.../pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json` |

Both rows record `metadata.actual_file_path` under `/app/data/sandboxes/.../current/artifacts/pd_storyboard_gen/fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218/`.

## Diagnostic Run Evidence

Command:

```bash
docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -A -F ' | ' -c "select command_id,status,accepted_task_id,metadata::jsonb->>'dispatch_status' as dispatch_status,metadata::jsonb#>>'{meeting_orchestration,status}' as mo_status,metadata::jsonb#>>'{meeting_orchestration,artifact_landing_status}' as artifact_landing_status,metadata::jsonb#>>'{meeting_orchestration,artifact_file_paths}' as artifact_file_paths from meeting_commands where command_id in ('cmd_aol_real_e2e_files_20260504_009','cmd_aol_real_e2e_files_20260504_010','cmd_aol_real_e2e_files_20260504_011','cmd_aol_real_e2e_files_20260504_012','cmd_aol_real_e2e_files_20260504_013','cmd_aol_real_e2e_files_20260504_014') order by created_at;"
```

Observed:

```text
cmd_aol_real_e2e_files_20260504_009 | completed | task_e208618064094a91 | completed | completed | not_requested | []
cmd_aol_real_e2e_files_20260504_010 | completed | task_469a9e1f08c640b2 | completed | completed | pending | []
cmd_aol_real_e2e_files_20260504_011 | completed | task_876d5d5a1d514bcd | completed | completed | pending | []
cmd_aol_real_e2e_files_20260504_013 | completed | task_f6434e989a904192 | completed | completed | landed | ["/app/data/.../pd_storyboard_manifest_c0bb574a-2458-404e-8fbc-396beb62219e.json"]
cmd_aol_real_e2e_files_20260504_014 | completed | task_fb5bd9966bc544f9 | completed | completed | landed | ["/app/data/.../pd_storyboard_proposal_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.md", "/app/data/.../pd_storyboard_manifest_fcc0c8d6-7b4b-4358-a1cd-5dd24c02d218.json"]
```

`cmd_aol_real_e2e_files_20260504_012` does not appear in this query; the observed `_012` attempt failed at local `curl` connection before a command row was accepted.

## Final Closure Evidence - `_021_tasklineage`

Command:

```bash
curl -sS -m 660 --fail-with-body -H 'Content-Type: application/json' --data-binary @/private/tmp/aol_e2e_021_tasklineage.json http://127.0.0.1:8220/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/meetings/0f2463d0-2f22-4016-9b5d-cb3b389eb8d1/commands
```

Observed command result:

```json
{
  "command_id": "cmd_aol_real_e2e_files_20260504_021_tasklineage",
  "status": "completed",
  "task_ir_id": "task_f385ff20d3364399",
  "dispatch_status": "completed",
  "execution_id": "7ba39e58-e19f-4113-b8db-5547558e26bd",
  "artifact_landing_status": "landed",
  "artifact_db_ids": [
    "42e2c149-3c1e-42eb-aa58-d472437a55af",
    "18420a74-86c5-4853-923a-1753c8ca8bb9",
    "632f963a-a209-4a7e-b478-da165f2da2a2"
  ],
  "artifact_file_paths": [
    "/app/data/sandboxes/.../pd_storyboard_contact_sheet_7ba39e58-e19f-4113-b8db-5547558e26bd.svg",
    "/app/data/sandboxes/.../pd_storyboard_proposal_7ba39e58-e19f-4113-b8db-5547558e26bd.md",
    "/app/data/sandboxes/.../pd_storyboard_manifest_7ba39e58-e19f-4113-b8db-5547558e26bd.json"
  ],
  "request_contract_aol_metadata_persisted": true
}
```

Artifact DB rows:

```text
632f963a-a209-4a7e-b478-da165f2da2a2 | data  | thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1 | task_id=task_f385ff20d3364399 | eval_passed=true
18420a74-86c5-4853-923a-1753c8ca8bb9 | draft | thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1 | task_id=task_f385ff20d3364399 | eval_passed=true
42e2c149-3c1e-42eb-aa58-d472437a55af | image | thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1 | task_id=task_f385ff20d3364399 | eval_passed=true
```

Filesystem evidence:

```text
pd_storyboard_contact_sheet_7ba39e58-e19f-4113-b8db-5547558e26bd.svg: SVG Scalable Vector Graphics image
pd_storyboard_proposal_7ba39e58-e19f-4113-b8db-5547558e26bd.md: UTF-8 text
pd_storyboard_manifest_7ba39e58-e19f-4113-b8db-5547558e26bd.json: JSON data
```

Raw file head checks:

```text
SVG: 00000000: 3c73 7667 2078 6d6c 6e73 3d22 6874 7470  <svg xmlns="http
MD:  00000000: 2320 5065 7266 6f72 6d61 6e63 6520 4469  # Performance Di
```

Artifact API evidence:

```bash
curl -sS -m 20 'http://localhost:8220/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/artifacts?thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1&limit=3'
```

Observed: response includes the `_021` contact-sheet image, proposal draft, and manifest data artifacts with `execution_id=7ba39e58-e19f-4113-b8db-5547558e26bd`, `thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1`, and file paths under `/app/data/sandboxes/.../current/artifacts/pd_storyboard_gen/7ba39e58-e19f-4113-b8db-5547558e26bd/`. The response reported `total=9` because older `_019` / `_020` artifacts share the same meeting thread; `limit=3` returned the newest `_021` set.

Core runtime pack-rule exclusion evidence:

```bash
rg -n "pd_storyboard_evidence|storyboard_preview|selected_scene_package_selector" backend/app/services backend/app/models backend/tests
```

Observed: no matches. Pack-specific storyboard evidence is emitted by `capabilities/performance_direction` and carried through generic artifact metadata; local-core runtime services do not infer PD storyboard evidence.

## Current Remaining Scope

Closed for this tested fixture:

- Meeting-led transport from AOL refs through MeetingEngine and downstream PD dispatch.
- 90 秒 reels storyboard proposal: 9 scenes, 10 seconds each, total 90 seconds.
- Storyboard frame/image artifact: contact-sheet SVG file plus per-scene `storyboard_frame` metadata.
- DB/file landing: three artifacts table rows and three concrete files.
- Meeting asset lane data path: `/artifacts?thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1` returns the landed artifact rows.
- Pack-owned review carrier: per-scene `meeting_discussion_prompt`, `decision_items`, `review_candidates`, and `approval_state=needs_review`.

Still not claimed by this run:

- Final rendered video or raster production frames beyond the SVG storyboard contact sheet.
- A live human review session resolving each per-scene decision.
- Exhaustive coverage for every future pack/object fixture.

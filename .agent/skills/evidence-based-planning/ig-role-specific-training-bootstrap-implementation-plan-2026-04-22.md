# IG Role-Specific Training Bootstrap Implementation Plan

Date: 2026-04-22
Status: Source-verified planning draft. Runtime and installed-pack validation are still pending.
Scope: `mindscape-ai-cloud` IG refs intake + `character_training` dataset prepare path
E2E Final Verification: `false` until the account-scoped end-to-end run below passes on `@jc6jf4.__`.

## Backup

If validation will touch a shared local-core database or draft candidate state, snapshot Postgres first:

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_ig_role_bootstrap_$(date +%Y%m%d_%H%M%S).sql
```

## Problems

1. **IG analysis stops at hints instead of producing reusable role-specific training base assets**: the IG pipeline captures training annotations, lane hints, and loose identity/look grouping cues, but it does not persist canonical face/body/full-person preprocess assets that CT can consume directly. Evidence: E1, E2, E3, E4.
2. **CT dataset materialization still starts from the raw IG image path**: the current materializer resolves a reference to the original `.jpg/.png` next to IG metadata, so the expensive analysis step does not eliminate later manual crop selection. Evidence: E5, E6.
3. **Role-specific intent taxonomy already exists, but CT runtime execution still routes mostly by coarse `dataset_profile`**: the repo already defines `identity_face_core_lora`, `identity_body_anchor_lora`, `identity_full_person_lora`, and `style_variant_lora`, and refs intake already recommends them from IG evidence, yet planner/materializer/augmentation still lack a first-class `identity_variant_role` execution contract. Evidence: E7, E8, E10, E11, E17, E18, E19, E20.
4. **Refs-grid review is good enough for batch intake, but downstream identity routing and stale-candidate enrichment are still manual and lossy**: the refs surface can already filter by source account, lane hint, identity cluster, and look state, yet the intake modal only supports manual create/append, the current `source_refs` payload drops the grouping and quality hints needed later, and duplicate append currently discards richer re-intake metadata. Evidence: E12, E13, E14, E15, E22.
5. **IG-derived candidates are intentionally not auto-authorized for `production_identity` synthetic prep**: current candidate taxonomy enrichment marks IG-derived candidates as `production_identity_candidate = False`, so body/full-person synthetic prepare cannot be unlocked safely without an explicit operator-selected production route plus new quality gates. Evidence: E20, E21.
6. **The repo currently uses “solve/formal asset” language for the 3D/Blender lane, not for LoRA dataset prepare**: implementing this work inside the existing IG 3D solve path would land the change in the wrong subsystem. Evidence: E16.

## Evidence

- **E1**: `capabilities/ig/models/vision_schema_models.py:311-339` defines `TrainingAnnotations` with `training_lane_hints`, `training_readiness`, `identity_cluster_hint`, and `look_state_hint`.
- **E2**: `capabilities/ig/models/vision_prompt_builder.py:239-264` explicitly asks the vision model to infer `training_lane_hints`, loose `identity_cluster_hint`, and loose `look_state_hint`.
- **E3**: `capabilities/ig/tools/ig_analyze_reference_pipeline.py:1234-1252` fails capture-safe visual-anatomy analysis if substantive training annotations are missing, proving these annotations are treated as first-class output.
- **E4**: `capabilities/ig/services/projection_builder.py:252-303` projects lane hints, quality flags, `p_training_identity_cluster_hint`, and `p_training_look_state_hint` into the refs index.
- **E5**: `capabilities/character_training/services/training_dataset_materializer.py:22-91` materializes datasets by resolving `source_refs` into `prepared_assets`; no preprocess asset stage is introduced before that handoff.
- **E6**: `capabilities/character_training/services/training_dataset_materializer.py:166-215` resolves an IG reference to its metadata JSON and the adjacent original image file, then builds the local asset payload from that original image path.
- **E7**: `capabilities/character_training/services/training_planner.py:178-206` only invokes augmentation for `production_identity` and `face_bootstrap_identity`.
- **E8**: `capabilities/character_training/services/training_dataset_augmentation_service.py:891-1018` confirms augmentation is implemented only for `production_identity` and `face_bootstrap_identity`.
- **E9**: `capabilities/character_training/services/training_dataset_augmentation_service.py:726-828` contains the canonical-front seed crop path used by face bootstrap.
- **E10**: `capabilities/character_training/services/training_dataset_augmentation_service.py:1032-1089` gives face bootstrap a dedicated multi-angle headshot variant set, while the non-face path only exposes `portrait_front`, `three_quarter_upper_body`, and `standing_full_body`.
- **E11**: `capabilities/ig/ui/modules/referencesPanel/useReferencesFetchLifecycle.ts:220-343` shows refs filters and facets already support `training_lane_hint`, `identity_cluster_hint`, and `look_state_hint`.
- **E12**: `capabilities/ig/ui/modules/ReferencesPanel.tsx:543-620` shows the refs grid already supports batch `Add To Training`.
- **E13**: `capabilities/ig/ui/modules/AddToTrainingCandidateModal.tsx:113-220` shows the modal currently supports only manual `create` vs `append` mode and a manual dataset-profile choice.
- **E14**: `capabilities/ig/ui/modules/useTrainingCandidateIntakeModal.ts:118-145` shows the `source_refs` payload only persists `reference_id`, `source_handle`, `source_shortcode`, `analysis_status`, `workspace_id`, `metadata`, and optional `analysis_profile`.
- **E15**: `capabilities/character_training/services/candidate_intake_contracts.py:39-80` normalizes arbitrary `source_ref` keys but deduplicates by `reference_id` or `source_shortcode`, which means later re-intake of the same ref will be counted as duplicate instead of merging richer metadata into the existing payload.
- **E16**: `capabilities/ig/ui/modules/visionAnalysisDetail/VisionAnalysis3DAssetsTab.tsx:1729-1818` uses “發送角色解算” and “發送正式場景資產” for the Blender/3D lane, not for LoRA dataset prepare.
- **E17**: `capabilities/character_training/services/training_intent_presets.py:115-168` already defines `identity_face_core_lora`, `identity_body_anchor_lora`, `identity_full_person_lora`, and `style_variant_lora` with `identity_variant_role`.
- **E18**: `capabilities/ig/ui/modules/trainingIntakeRecommendations.ts:83-200` already recommends face/body/full-person/style intent presets from lane hints and visible body/style signals.
- **E19**: `capabilities/ig/ui/modules/AddToTrainingCandidateModal.tsx:148-170` only exposes `reference_only` and `face_bootstrap_identity` as operator-visible dataset-profile routes.
- **E20**: `capabilities/character_training/services/training_dataset_profiles.py:12-140` only declares `reference_only`, `face_bootstrap_identity`, and `production_identity`; `normalize_dataset_profile` and `default_target_asset_count_for_profile` remain profile-centric.
- **E21**: `capabilities/character_training/services/candidate_store.py:137-143` explicitly sets `production_identity_candidate = False` for IG-derived taxonomy inference, keeping IG hints from auto-unlocking the stricter production route.
- **E22**: `capabilities/character_training/services/training_caption_builder.py:61-100` already consumes `source_ref.look_state_hint` and `source_ref.identity_cluster_hint`, proving CT can benefit immediately once these fields are persisted.

## Working Decisions

- **Wave-1 contract**: keep `dataset_profile` as the coarse policy switch (`reference_only`, `face_bootstrap_identity`, `production_identity`) and do **not** add new dataset-profile enums in the first implementation wave.
- **Runtime selector**: make `identity_variant_role` the first-class role selector inside planner/materializer/augmentation for `face_core`, `body_anchor`, `full_person`, and `style_variant`.
- **Preprocess policy**: preserve source aspect ratio and geometry metadata; do not globally crop/resize the entire dataset to a fixed training size in preprocess. Bucketed trainers should continue to own final size handling.
- **Synthetic policy**: `style_variant` stays raw-ref-only in wave 1; `body_anchor` / `full_person` synthetic expansion is allowed only on an explicit operator-selected production route with quality gates.

## Proposed Changes

### Change 1: Persist the full CT-relevant IG training-hint subset into `source_refs`
Resolves Problem #4.

- Extend `buildSourceRefsPayload` in `capabilities/ig/ui/modules/useTrainingCandidateIntakeModal.ts` so each IG `source_ref` carries the training metadata CT will need later:
  - `training_lane_hints`
  - `identity_cluster_hint`
  - `look_state_hint`
  - `training_readiness`
  - `training_source_kind`
  - `dataset_mix_role`
  - `primary_subject_clarity`
  - `subject_framing`
  - `face_visibility`
  - `body_orientation`
  - `silhouette_clarity`
  - `garment_fit_signal`
  - `look_variant_level`
  - `style_tags`
  - `quality_flags`
  - `hard_blockers`
  - `proportion_stability_risk`
  - `camera_distortion_risk`
  - `training_notes`
- Map IG refs-grid projection fields (`p_training_*`) into canonical CT `source_ref` keys without the `p_` prefix so downstream CT code does not need IG-specific field names.
- Keep the existing lightweight identifier fields, but stop dropping the evidence that already exists in the refs index.
- Do not derive a final “same person” truth here; persist loose source-side hints exactly as hints.

Ordering:

- Do this before any CT-side preprocess work so the new asset pipeline has the metadata it needs from the first prepare run.

Verification target:

- A newly created or appended candidate retains the richer IG hints inside `source_refs_json`.

### Change 2: Change `source_ref` dedupe from “drop duplicate” to “merge duplicate metadata”
Resolves Problem #4.

- Update `merge_source_refs` in `capabilities/character_training/services/candidate_intake_contracts.py` so duplicate IG refs preserve or merge newer structured metadata instead of silently discarding it.
- Merge should remain keyed by `reference_id` / `source_shortcode`, but the payload should be reconciled field-by-field.
- Prefer non-empty incoming training metadata when the existing record lacks it, but do not erase stable existing identifiers with blank incoming values.
- Treat `metadata` and any future nested training-hint payloads as deep-merge objects rather than replace-only blobs.
- Keep dedupe counts and identity stable; this is a payload-enrichment fix, not a change to candidate cardinality.

Ordering:

- Land this immediately after Change 1 so repeated intake from refs grid can enrich older candidates without forcing destructive rewrites.

Verification target:

- Re-adding the same ref to an existing candidate updates missing training metadata rather than doing nothing.

### Change 3: Add an explicit stale-draft backfill path for existing IG candidates
Resolves Problems #4 and #5.

- Add a one-shot maintenance path for existing draft candidates whose `source_refs_json` predates the richer IG training-hint payload.
- Preferred implementation: a dedicated CT-side maintenance script or admin endpoint that scans draft `ig_refs` candidates, resolves each `reference_id` against the IG refs index, and enriches missing `source_ref` fields in place using the same field-merge contract from Change 2.
- Keep this backfill scoped to `draft` candidates only in wave 1.
- Include a dry-run mode and per-candidate diff output before any write path is allowed.

Ordering:

- Land after Change 2 and run it before broad operator rollout, so candidate auto-suggest and role-aware prepare do not depend on users manually re-intaking old refs.

Verification target:

- A pre-existing draft candidate created before this project gains the missing IG training metadata without duplicating refs or changing candidate identity.

### Change 4: Add a CT-side canonical preprocess stage for role-specific base assets
Resolves Problems #1 and #2.

- Introduce a preprocess layer ahead of today’s augmentation fanout, owned by `character_training`, not by IG and not by the Blender solve lane.
- Extend `TrainingDatasetMaterializer` or a new adjacent helper so IG refs can resolve into one or more role-specific prepared base assets:
  - `face_core`: canonical face crop seed
  - `body_anchor`: body-anchor crop with silhouette and garment-fit preservation
  - `full_person`: full-person anchor crop that preserves stance and proportions
- Persist these as explicit prepared assets with metadata describing:
  - `preprocess_role`
  - `source_reference_id`
  - `source_image_path`
  - `derived_from_training_hints`
  - crop geometry
  - preprocess policy
  - `quality_gate_flags`
  - `mask_strategy`
  - optional `mask_path`
- Use the existing raw IG image as the fallback source of truth, but stop treating it as the only base asset once role-specific preprocess succeeds.
- Preserve raw aspect ratio on prepared assets unless a role-specific crop is required; do not add a blanket resize-to-training-resolution step in this preprocess layer.

Insertion points:

- `capabilities/character_training/services/training_dataset_materializer.py`
- potentially a new helper module under `capabilities/character_training/services/`

Ordering:

- Land the preprocess stage before expanding augmentation contracts; otherwise body/full-person variants will still fan out from the wrong starting image.

Verification target:

- Dataset prepare produces explicit preprocess assets before any synthetic augmentation begins.

### Change 5: Make `identity_variant_role` a first-class runtime contract and define profile policy
Resolves Problems #3 and #5.

- Pass the active intent, `identity_variant_role`, and declared `dataset_profile` from `training_planner` into materializer and augmentation so the service can distinguish:
  - face core
  - body anchor
  - full person
  - style variant
- Define the wave-1 policy explicitly:
  - `face_core` + `face_bootstrap_identity`: canonical face seed + existing multi-angle synthetic face bootstrap
  - `body_anchor` + `reference_only`: body-anchor preprocess only, no synthetic fanout
  - `full_person` + `reference_only`: full-person preprocess only, no synthetic fanout
  - `body_anchor` / `full_person` + `production_identity`: role-aware preprocess plus curated synthetic fanout
  - `style_variant`: raw/preprocessed refs only, no synthetic augmentation in wave 1
- Keep `face_bootstrap_identity` for the current face workflow, but stop using `production_identity` as an implicit catch-all non-face path.
- Update production gating so IG-derived candidates still do **not** auto-qualify, but an explicit operator-selected production route may proceed for `body_anchor` / `full_person` only when new quality gates pass.
- Avoid inventing a scene/runtime selector here; this remains a dataset-prepare concern inside CT.

Insertion points:

- `capabilities/character_training/services/training_planner.py`
- `capabilities/character_training/services/training_dataset_augmentation_service.py`
- `capabilities/character_training/services/training_dataset_profiles.py`

Ordering:

- Land after Change 3, because role-aware augmentation needs the preprocess assets.

Verification target:

- Face intents still use the mature face-bootstrap path.
- Body intents no longer fall back to face-centric assets.
- Full-person intents preserve stance/proportion signals in their prepared set.
- Explicit `production_identity` runs for body/full-person only proceed when the new gates pass.

### Change 6: Add refs-grid candidate auto-suggest and grouping assist
Resolves Problem #4.

- Keep the existing manual create/append control, but pre-suggest a target candidate using:
  - exact or dominant `identity_cluster_hint`
  - compatible `look_state_hint`
  - matching `source_handle`
  - existing candidate active intent roles
- Score against candidate `source_refs` and `metadata.training_intake.intents`, not just display name.
- Surface the suggestion in `AddToTrainingCandidateModal` as a recommendation, not as silent auto-merge.
- Keep operator confirmation mandatory.

Insertion points:

- `capabilities/ig/ui/modules/AddToTrainingCandidateModal.tsx`
- `capabilities/ig/ui/modules/useTrainingCandidateIntakeModal.ts`
- optionally a small shared helper under `capabilities/ig/ui/modules/`

Ordering:

- This can land in parallel with Change 3 if the metadata propagation from Change 1 is already merged.

Verification target:

- Refs-grid batch review stays lightweight, but common same-identity append flows no longer require scanning the full draft-candidate list manually.

### Change 7: Keep LoRA bootstrap work explicitly out of the IG 3D solve/formal asset lane
Resolves Problem #6.

- Do not add this work to `VisionAnalysis3DAssetsTab`, Blender Preflight, or world handoff flows.
- If the product needs a new operator-visible entry point, add it under CT dataset prepare or refs-to-training intake, not under IG scene/character solve.
- Update UI copy or docs only if needed to keep this boundary explicit.

Ordering:

- Apply as a guardrail throughout the implementation, not as a final cleanup.

Verification target:

- No new CT dataset-prep actions appear under the existing 3D solve controls.

## Verification SOP

1. **Source-ref payload verification**
   Run the IG refs intake modal in a local dev session and inspect the candidate create/append request payload.
   Pass: `source_refs[]` contains `training_lane_hints`, `identity_cluster_hint`, and `look_state_hint`.
   Fail: the request still only carries `reference_id`/`handle`/`shortcode` plus generic metadata.
   Proves: Problems #1 and #4 are being addressed at the handoff boundary.

2. **Duplicate-ref merge verification**
   Create a draft candidate from one ref, then re-intake the same ref after enriching the IG-side metadata.
   Pass: the candidate retains one logical ref entry and the richer structured metadata is present after append.
   Fail: append reports deduped and the source-ref payload remains stale.
   Proves: Problem #4.

3. **Draft-candidate backfill verification**
   Run the maintenance backfill path against an older draft candidate created before the new IG payload fields existed.
   Pass: the candidate gains missing training metadata in-place, reports a meaningful diff, and retains one logical ref entry per reference.
   Fail: the backfill no-ops on stale refs, creates duplicates, or mutates non-draft candidates.
   Proves: Problems #4 and #5.

4. **Prepared-base-asset verification**
   Run CT dataset prepare for one face intent, one body intent, and one full-person intent using IG refs only.
   Pass: the dataset contains explicit prepared base assets for the active role before synthetic variants are appended, and prepared asset metadata includes crop geometry plus mask/quality policy fields when applicable.
   Fail: only the original IG image path appears as the base asset for every role.
   Proves: Problems #1 and #2.

5. **Role-aware runtime-contract verification**
   Prepare datasets for:
   - `identity_face_core_lora`
   - `identity_body_anchor_lora`
   - `identity_full_person_lora`
   Run each intent once on `reference_only` and, where allowed, once on explicit `production_identity`.
   Pass: face keeps the existing headshot/bootstrap behavior; body/full-person runs produce role-appropriate prepared assets; synthetic body/full-person fanout occurs only on explicit production route with passing gates.
   Fail: body/full-person still route through the same face-oriented or generic raw-image-only path, or production fanout occurs without explicit production route.
   Proves: Problems #3 and #5.

6. **Refs-grid operator flow verification**
   From refs grid:
   - filter by one `identity_cluster_hint`
   - multi-select refs
   - choose `Add To Training`
   Pass: the modal presents a recommended existing candidate when strong grouping evidence exists, while still allowing override.
   Fail: the operator must always manually search the draft list with no assist.
   Proves: Problem #4.

7. **Subsystem-boundary verification**
   Review IG detail and CT workbench surfaces after the change.
   Pass: new dataset/bootstrap actions live under CT prepare/intake surfaces, not under Blender solve/formal asset controls.
   Fail: CT bootstrap actions appear in the 3D solve lane.
   Proves: Problem #6.

## E2E Final Verification Gate

- **Target account**: `@jc6jf4.__`
- **Current gate state**: `false`
- **State semantics**:
  - Set to `true` only after the complete account-scoped operator flow below passes end-to-end on the installed system.
  - Keep `false` if any step is blocked, skipped, regresses, or still requires source-only/manual inference.

### Account-scoped E2E flow for `@jc6jf4.__`

1. **Account browse and refs visibility**
   Open the IG account surface for `@jc6jf4.__`, confirm refs grid can browse that account’s refs, and confirm refs carry training facets (`training_lane_hint`, `identity_cluster_hint`, `look_state_hint`, dataset-intake badges).
   Pass: refs from `@jc6jf4.__` are visible and filterable from the account/refs surfaces.
   Fail: refs are missing, stale, or do not expose the projected training-hint facets.

2. **Batch intake operator flow**
   From refs grid, multi-select a coherent batch from `@jc6jf4.__`, open `Add To Training`, and validate:
   - recommended intent selection
   - recommended append target when same-identity evidence exists
   - manual override still works
   - `reference_only`, `face_bootstrap_identity`, and explicit `production_identity` routes are selectable where relevant
   Pass: the operator can finish intake without manual candidate-list hunting or retyping intent configuration.
   Fail: the flow still needs full manual candidate lookup or does not expose the expected route controls.

3. **Legacy draft enrichment**
   Run the stale-draft backfill path against any pre-existing `draft` candidate sourced from `@jc6jf4.__`.
   Pass: dry-run emits meaningful per-candidate/per-ref diff output, apply mode enriches missing `source_ref` training hints in place, and candidate identity/ref cardinality stay stable.
   Fail: dry-run has no actionable diff on obviously stale candidates, apply mutates non-draft candidates, creates duplicates, or drops existing metadata.

4. **Face route verification**
   Prepare `identity_face_core_lora` for `@jc6jf4.__` on `face_bootstrap_identity`.
   Pass: CT materialization records `preprocess_role = face_core`; face bootstrap still follows the mature face-only synthetic route; output dataset reaches the expected prepared asset count.
   Fail: face route no longer bootstraps correctly, or loses the canonical face/bootstrap behavior.

5. **Body route verification**
   Prepare `identity_body_anchor_lora` for `@jc6jf4.__` on:
   - `reference_only`
   - explicit `production_identity`
   Pass: `reference_only` yields body-anchor preprocess metadata with no synthetic fanout; explicit `production_identity` only fans out when quality gates pass.
   Fail: body still routes through face/generic raw-only behavior, or production fanout occurs without the explicit production route plus passing gates.

6. **Full-person route verification**
   Prepare `identity_full_person_lora` for `@jc6jf4.__` on:
   - `reference_only`
   - explicit `production_identity`
   Pass: full-person prepare preserves stance/proportion signals in the prepared set; explicit production fanout remains gate-controlled.
   Fail: full-person loses stance/proportion semantics or silently collapses back to generic portrait flow.

7. **Style route verification**
   Prepare `style_variant_lora` for `@jc6jf4.__`.
   Pass: style route stays raw/preprocessed-ref-only and does not trigger synthetic expansion in wave 1.
   Fail: style route reuses identity synthetic fanout or loses the style-hint metadata.

8. **Subsystem boundary check**
   After the above runs, inspect IG detail and CT surfaces.
   Pass: no new LoRA bootstrap action appears under Blender/3D solve/formal asset controls.
   Fail: the feature leaks into the 3D solve lane.

### Final gate rule

- Mark **E2E Final Verification = `true`** only if all eight steps above pass on `@jc6jf4.__` without manual data surgery outside the intended operator flow.
- Otherwise keep **E2E Final Verification = `false`** and record the exact failing step number plus blocking symptom.

## Automated Test Plan

- Extend `capabilities/ig/ui/modules/AddToTrainingCandidateModal.test.tsx`.
  Scenario: refs with shared `identity_cluster_hint` and matching lane hints open the modal.
  Assert: the suggested draft candidate is preselected or surfaced as recommended, while manual override remains available.
  Prevents regression of Problem #4.

- Add or extend tests around `capabilities/ig/ui/modules/useTrainingCandidateIntakeModal.ts`.
  Scenario: `buildSourceRefsPayload` is called with refs containing IG training metadata.
  Assert: the payload preserves lane hints, identity cluster, look-state fields, and the broader body/full-person quality-hint subset.
  Prevents regression of Problems #1 and #4.

- Add tests for the stale-draft backfill utility or endpoint introduced in Change 3.
  Scenario: an existing `draft` IG candidate has legacy `source_refs_json` without the new training-hint fields.
  Assert: backfill enriches only missing fields, skips non-draft candidates, and produces stable per-ref merge results.
  Prevents regression of Problems #4 and #5.

- Extend `capabilities/character_training/tests/training_dataset_materializer_test.py`.
  Scenario: IG refs with role-specific metadata are materialized.
  Assert: prepared base assets include explicit preprocess-role metadata, crop geometry, and mask/quality policy metadata, and do not rely only on the original image path.
  Prevents regression of Problems #1 and #2.

- Extend `capabilities/character_training/tests/training_planner_service_test.py`.
  Scenario: prepare dataset for face/body/full-person intents using the same candidate.
  Assert: planner passes `identity_variant_role` and declared `dataset_profile` into dataset prepare and augmentation correctly.
  Prevents regression of Problems #3 and #5.

- Extend `capabilities/character_training/tests/face_bootstrap_workflow_contract_test.py` and add a sibling test module for body/full-person bootstrap contracts if a new workflow contract is introduced.
  Scenario: body/full-person roles choose their own preprocess and variant contract.
  Assert: body/full-person do not silently reuse the face-only contract.
  Prevents regression of Problem #3.

- Add tests for `capabilities/character_training/services/candidate_intake_contracts.py`.
  Scenario: append duplicate `reference_id` with richer metadata.
  Assert: merge preserves one logical ref entry and updates missing structured fields.
  Prevents regression of Problem #4.

- Add tests for `capabilities/character_training/services/training_dataset_profiles.py` and augmentation gating.
  Scenario: IG-derived body/full-person intent requests `production_identity`.
  Assert: synthetic fanout is blocked without explicit production route or failing quality gates, and allowed only when both conditions are satisfied.
  Prevents regression of Problem #5.

## Risks / Open Questions

- **Risk**: `identity_cluster_hint` and `look_state_hint` are intentionally loose cues, not canonical identity truth. Auto-suggest should remain advisory until real-world precision is measured.
- **Risk**: body-anchor crop quality may require a detector or heuristic stronger than the current face-centric crop path; otherwise the new preprocess layer may still need human correction.
- **Risk**: body/full-person synthetic fanout may need stricter pose/limb quality gates than face bootstrap to avoid low-quality backup assets.
- **Risk**: changing `merge_source_refs` semantics can affect any caller that currently relies on “duplicate means ignore”; verify non-IG CT paths before rollout.
- **Risk**: the stale-draft backfill utility must ship with dry-run output and draft-only scope to avoid surprising mutations.
- **Decision**: do not add new dataset-profile enums in wave 1; keep body/full-person as role-aware branches under the existing profile system and revisit only if the contract becomes too implicit.
- **Open question**: whether style-only intents should ever generate synthetic references, or should remain raw-ref-only by policy.
- **Open question**: whether prepared preprocess assets should be cached back into IG reference storage, or remain CT-owned artifacts only.
- **Open question**: whether wave 1 should generate actual segmentation masks, or only persist mask-ready metadata and crop geometry for a later masked-training rollout.

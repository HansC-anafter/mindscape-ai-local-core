---
playbook_code: divi_content_update
version: 1.0.0
capability_code: web_generation
name: Divi Content Update
description: |
  Safely update WordPress Divi site content using Divi Safeguard mechanism.
  Includes 7 execution steps: Pre-Flight validation, health check, mapping validation,
  Patch Plan validation (requires Gate), pre-apply validation (requires Gate),
  apply Patch, and verify result.
  All steps generate RunStep, and Gate steps generate GateInfo for Thread View display.
tags:
  - web
  - divi
  - wordpress
  - content-update
  - safeguard
  - gated-workflow

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
  - gated
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - web_generation.divi_preflight_validation
  - web_generation.divi_health_check
  - web_generation.divi_mapping_validation
  - web_generation.divi_patch_plan_validation
  - web_generation.divi_apply_gate_validation
  - web_generation.divi_apply_patch
  - web_generation.divi_verify_update

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🛡️
---

# Divi Content Update - SOP

## Objective

Safely update WordPress Divi site content using Divi Safeguard mechanism, ensuring:

1. **Safety Validation**: Pre-Flight checks ensure environment and configuration are correct
2. **Health Check**: Verify WordPress site accessibility
3. **Mapping Validation**: Ensure page and template mappings are correct
4. **Patch Plan Validation**: Validate update plan meets specifications (requires Gate approval)
5. **Pre-Apply Validation**: Final check and create checkpoint (requires Gate approval)
6. **Safe Apply**: Execute update and record revision
7. **Result Verification**: Verify update succeeded

**Core Value**:
- Multi-layer Gate safeguard mechanism ensures update safety
- Complete execution chain tracking (RunStep)
- Gate approval flow integrated with Thread View
- Automatic rollback support

## Execution Steps

### Phase 0: Pre-Flight Validation (Gate 0)

**Execution Order**:
1. Step 0.0: Pre-Flight Validation

#### Step 0.0: Pre-Flight Validation

**Tool**: `web_generation.divi_preflight_validation`

**Inputs**:
- `workspace_id`: From context
- `site_id`: From input
- `page_ids`: From input
- `content_source`: From input (optional)

**Validation Items**:
- site_id format and DB consistency
- API Key availability (prioritize DB, environment variable as fallback)
- Target pages in registry
- Pages have slot_schema
- API Key hardcoding check (optional)
- post_content direct modification check (optional)
- Currency symbol check (optional)

**Outputs**:
- `preflight_result`: Validation result (includes passed, checks, blocking_failures)
- `runstep`: Pre-Flight Validation RunStep

**Gate**: None (auto-execute)

**On Failure**: Stop execution and return error if `blocking_failures > 0`

---

### Phase 1: Health Check (Gate 1)

**Execution Order**:
2. Step 1.0: WordPress Site Health Check

#### Step 1.0: Health Check

**Tool**: `web_generation.divi_health_check`

**Inputs**:
- `workspace_id`: From context
- `site_id`: From input

**Validation Items**:
- WordPress Plugin API health status
- Site accessibility

**Outputs**:
- `health_result`: Health check result (includes status, passed)
- `runstep`: Health Check RunStep

**Gate**: None (auto-execute)

**On Failure**: Stop execution and return error if `status != "healthy"`

---

### Phase 2: Mapping Validation (Gate 2)

**Execution Order**:
3. Step 2.0: Mapping Validation

#### Step 2.0: Mapping Validation

**Tool**: `web_generation.divi_mapping_validation`

**Inputs**:
- `workspace_id`: From context
- `site_id`: From input
- `page_ids`: From input

**Validation Items**:
- Pages exist in registry
- Pages have valid template_id
- Pages have slot_schema
- Templates exist in registry

**Outputs**:
- `mapping_result`: Mapping validation result (includes passed, errors, warnings)
- `runstep`: Mapping Validation RunStep

**Gate**: None (auto-execute)

**On Failure**: Stop execution and return error if `passed == false`

---

### Phase 3: Patch Plan Validation (Gate 3)

**Execution Order**:
4. Step 3.0: Patch Plan Validation

#### Step 3.0: Patch Plan Validation

**Tool**: `web_generation.divi_patch_plan_validation`

**Inputs**:
- `patch_plan`: From input
- `scope_page_ids`: From input
- `target_slot_ids`: From input (optional)
- `template_schemas`: From registry (optional)
- `run_id`: From context

**Validation Items**:
- patch_plan.operations is not empty
- operation.page_id exactly matches scope.pages
- slots only contain target slot_ids (no extra modifications)
- SlotSchemaValidator validation passes

**Outputs**:
- `patch_plan_result`: Patch Plan validation result (includes passed, errors)
- `runstep`: Patch Plan Validation RunStep (status=WAITING_GATE)
- `gate_info`: GateInfo object (if passed)

**Gate**: **Requires Gate Approval** 🚧

**Gate Type**: Validation

**On Failure**: Stop execution and return error if `passed == false`

**After Gate Approval**: Continue to next step

---

### Phase 4: Pre-Apply Validation (Gate 4)

**Execution Order**:
5. Step 4.0: Pre-Apply Validation

#### Step 4.0: Pre-Apply Validation

**Tool**: `web_generation.divi_apply_gate_validation`

**Inputs**:
- `workspace_id`: From context
- `site_id`: From input
- `page_ids`: From input
- `mode`: From input ("draft" or "publish")
- `diff_reviewed`: From input (optional, default false)
- `run_id`: From context
- `checkpoint_id`: Auto-generated

**Validation Items**:
- mode confirmation (publish mode requires confirmation)
- Diff review confirmation
- Record current revision_ids (for rollback)

**Outputs**:
- `apply_gate_result`: Pre-apply validation result (includes passed, checks, current_revisions)
- `runstep`: Apply Gate RunStep (status=WAITING_GATE)
- `gate_info`: GateInfo object
- `checkpoint_id`: Checkpoint ID (for rollback)

**Gate**: **Requires Gate Approval** 🚧

**Gate Type**: Modification

**On Failure**: Stop execution and return error if `passed == false`

**After Gate Approval**: Continue to next step

---

### Phase 5: Apply Patch

**Execution Order**:
6. Step 5.0: Apply Patch

#### Step 5.0: Apply Patch

**Tool**: `web_generation.divi_apply_patch`

**Inputs**:
- `workspace_id`: From context
- `site_id`: From input
- `patch_plan`: From input
- `mode`: From input ("draft" or "publish")
- `pre_revision_ids`: From `apply_gate_result.current_revisions`
- `checkpoint_id`: From `apply_gate_result.checkpoint_id`

**Execution Items**:
- Call WordPressPluginClient.apply_patch_plan()
- Record DiviRevision (with required id)
- Mark other revisions as not current

**Outputs**:
- `apply_result`: Apply result (includes success, revision_ids, revisions)
- `runstep`: Apply Patch RunStep

**Gate**: None (auto-execute)

**On Failure**:
- If `success == false`, call RollbackService.automatic_rollback()
- Return error and rollback status

---

### Phase 6: Verify Result

**Execution Order**:
7. Step 6.0: Verify Result

#### Step 6.0: Verify Result

**Tool**: `web_generation.divi_verify_update`

**Inputs**:
- `workspace_id`: From context
- `site_id`: From input
- `page_ids`: From input

**Validation Items**:
- Use get_revision_diff() to verify each page's update
- Confirm revision was applied correctly

**Outputs**:
- `verify_result`: Verification result (includes success, results)
- `runstep`: Verify Result RunStep

**Gate**: None (auto-execute)

**On Failure**: Log verification failure but don't stop execution (apply already completed)

---

## Gate Approval Flow

### Gate 3: Patch Plan Validation

**When Triggered**: After Patch Plan validation passes

**Gate Info**:
- `operation`: `BATCH_UPDATE`
- `impact_summary`: Impact scope summary (page count, slot count)
- `affected_resources`: List of affected pages
- `checkpoint_required`: `false` (validation Gate)

**After Approval**: Continue to Gate 4

**After Rejection**: Stop execution, return error

### Gate 4: Pre-Apply Validation

**When Triggered**: After pre-apply validation passes

**Gate Info**:
- `operation`: `PUBLISH` (if publish mode)
- `impact_summary`: Final impact scope summary
- `affected_resources`: List of affected pages
- `checkpoint_required`: `true` (modification Gate, must have checkpoint)
- `checkpoint_id`: Checkpoint ID

**After Approval**: Continue to Apply Patch

**After Rejection**: Stop execution, return error

---

## RunStep and GateInfo Generation

All steps generate `RunStep` objects, including:

- `index`: Step index (0-6)
- `code`: Step code (preflight_validation, health_check, mapping_validation, patch_plan_validation, apply_gate, apply_patch, verify_result)
- `status`: Step status (COMPLETED, FAILED, WAITING_GATE)
- `requires_gate`: Whether Gate is required (Gate 3 and Gate 4 are true)
- `gate_status`: Gate status (pending, approved, rejected)
- `changes`: AffectedResource list
- `input_summary`: Input summary
- `output_summary`: Output summary

Gate 3 and Gate 4 additionally generate `GateInfo` objects, including:

- `run_id`: Run ID
- `operation`: GateableOperation
- `impact_summary`: Impact scope summary
- `affected_resources`: List of affected resources
- `checkpoint_required`: Whether checkpoint is required
- `checkpoint_id`: Checkpoint ID (Gate 4)

---

## Input Parameters

```yaml
workspace_id: string          # Required: Workspace ID (from context)
site_id: string              # Required: Site ID
page_ids: list[int]          # Required: List of page IDs to update
patch_plan: object           # Required: Patch Plan object
mode: string                 # Optional: Execution mode ("draft" or "publish"), default "draft"
content_source: string       # Optional: Content source path (for Pre-Flight scanning)
diff_reviewed: boolean       # Optional: Whether diff has been reviewed, default false
target_slot_ids: list[string] # Optional: Target slot IDs
```

---

## Output Results

```yaml
success: boolean             # Whether execution succeeded
run_id: string               # Run ID
steps: list[RunStep]         # List of RunStep objects for all steps
gates: list[GateInfo]        # List of GateInfo objects (Gate 3 and Gate 4)
checkpoint_id: string        # Checkpoint ID (generated by Gate 4)
preflight_result: object     # Pre-Flight validation result
health_result: object        # Health check result
mapping_result: object       # Mapping validation result
patch_plan_result: object    # Patch Plan validation result
apply_gate_result: object    # Pre-apply validation result
apply_result: object         # Apply result
verify_result: object        # Verification result
```

---

## Error Handling

### Automatic Rollback

If Apply Patch fails, automatically call `RollbackService.automatic_rollback()`:

- Use `pre_revision_ids` as rollback target
- Rollback all applied revisions
- Record rollback reason

### Gate Rejection

If Gate 3 or Gate 4 is rejected:

- Stop execution
- Return rejection reason
- Make no modifications

### Validation Failure

If any validation step fails:

- Stop execution
- Return detailed error message
- Make no modifications

---

## Related Documentation

- [Divi Safeguard Implementation Plan](../../docs/DIVI_SAFEGUARD_IMPLEMENTATION_PLAN.md)
- [Divi Safeguard Integration Guide](../../docs/DIVI_SAFEGUARD_INTEGRATION_GUIDE.md)
- [Thread View Component Specification](../../docs/THREAD_VIEW_COMPONENT_SPECIFICATION.md)

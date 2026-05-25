---
name: evidence-based-planning
description: Create implementation plans only after collecting evidence from code and runtime. Use for design docs, implementation plans, rollout plans, and refactor plans where every problem statement, insertion point, dependency, and verification step must be source-backed.
---

# Evidence-Based Planning

> Canonical copy: `mindscape-ai-cloud/.agent/skills/evidence-based-planning/SKILL.md`
> This local-core copy is kept as a runtime/UI mirror because local-core scans its own `.agent/skills/` directory.

Use this skill when the output is a plan, not code, and the plan must be defensible against the actual repo and runtime state.

This skill is stricter than normal planning:

- no problem statement without evidence
- no code change proposal without verified insertion points
- no validation section without concrete commands and pass/fail criteria

If the task also involves diagnosis, apply the rules from `evidence-based-reporting` first, then write the plan.

## Mindscape Entry Points

When creating a plan for Mindscape work, load and apply the matching entry point before defining problems or proposed changes:

| Plan scope | Required entry point |
|---|---|
| Pack development, pack-owned data plane, local-core runtime/data-plane boundary, installed-copy conflict | `mindscape-ai-cloud/docs/internal/local-core/PACK_AND_DATA_PLANE_DEVELOPER_GUIDE_2026-05-15.zh-TW.md` |
| PostgreSQL/runtime DB architecture, control-plane/data-plane split, row budgets, queue/runner DB guardrails | `mindscape-ai-cloud/docs/internal/runtime-database/README.md` |
| Capability packaging/install, `.mindpack`, install API, restart and post-install verification | `mindscape-ai-cloud/docs/internal/local-core/CAPABILITY_INSTALLATION_GUIDE.md` |
| Playbook plane responsibility and execution/control/governance/integration boundaries | `mindscape-ai-cloud/docs/architecture/playbook-implementation-guide.md` |
| General local-core boundaries, code style, documentation rules | `mindscape-ai-cloud/docs/internal/local-core/DEVELOPER_GUIDE_MINDSCAPE_AI.md` |

Internal implementation plans must be written under `mindscape-ai-cloud/docs/internal/local-core/` or the matching cloud internal docs directory. Do not create new plans under `mindscape-ai-local-core/docs-internal/`.

## Core Rule

**Do not write an implementation plan until the current system has been observed from the real sources of truth.**

Sources of truth include:

- code with file path and line references
- runtime state from commands, logs, APIs, or DB queries
- existing config actually loaded by the running process

Reading one file and extrapolating the rest is not evidence.

## Modular Entry Rule

**For inherited, large, or boundary-crossing changes, the implementation MUST begin by creating or selecting a modular entrypoint before changing behavior.**

Default stance:

- do not start by adding new logic directly into a god file
- first open a seam such as a facade, adapter, shim, dispatcher, extractor module, service split, or thin compatibility wrapper
- keep the legacy entrypoint as a thin caller when possible

This rule is mandatory for:

- inherited or AI-generated code
- multi-responsibility files
- cross-pack changes
- API, job, migration, runtime registry, artifact, or persistence boundary changes
- changes that touch more than one pack surface such as `api/`, `services/`, `tools/`, `schema/`, `ui/`, `jobs/`, or `workflows/`

Narrow exception:

- a leaf-only fix in a single low-risk file may skip a new seam
- the plan must state why the change is leaf-only, why no new boundary is being introduced, and why the choice does not increase future refactor cost

## Required Output Shape

Every implementation plan should contain these sections in this order:

1. Problem list
2. Evidence
3. Proposed changes
4. Verification SOP
5. Automated test plan
6. Risks / open questions

If the user wants a shorter plan, compress the prose, but keep the same logical order.

## Workflow

### Phase 1: Collect Evidence

Before defining problems, inspect the real system.

For each relevant component:

1. Read the exact code path.
2. Verify runtime state if the claim is about behavior, config, data, or process state.
3. Record evidence with file paths, line numbers, or command outputs.
4. Delay conclusions until evidence is collected.

For unfamiliar, AI-generated, outsourced, or inherited code, first build a review map before proposing changes:

- feature purpose and acceptance criteria
- module boundaries and main dataflow
- candidate modular entrypoints or seams for the first implementation cut
- source of truth for important data
- high-risk zones that need targeted line review
- current test, deploy, logging, and rollback coverage

For Mindscape capability packs, anchor the map to actual pack surfaces: `manifest.yaml`, `playbooks/specs/`, `tools/`, `services/`, `api/`, `schema/` or `schemas/`, `ui/`, `migrations/`, `jobs/`, `workflows/`, `evals/`, and `tests/`.

Minimum evidence standards:

| Claim Type | Required Evidence |
|---|---|
| Code behavior | file path + verified line numbers |
| Runtime behavior | logs, curl output, DB query, process inspection |
| Config source | actual config file plus runtime confirmation when relevant |
| Missing caller / dead code | full-project grep with explicit scope |
| Data availability | actual rows/files/index contents, not just schema |
| Dataflow / source of truth | caller/route trace + writer and reader code + runtime/API/DB evidence when relevant |

### Phase 2: Define Problems

Write concrete problems backed by the evidence from Phase 1.

Format:

```markdown
1. **Problem title**: one-sentence description. Evidence: E1, E4.
2. **Problem title**: one-sentence description. Evidence: E2, E3.
```

Rules:

- problems go before the solution
- every problem cites evidence
- do not mix diagnosis and fix in the same bullet
- if two problems share a symptom but have different causes, split them

### Phase 3: Prioritize

Score each problem before proposing changes.

Use:

- Severity `1-5`: impact if shipped unfixed
- Detection `1-5`: difficulty of catching it before production
- Priority = `Severity x Detection`

This prevents a plan from focusing on low-value cleanup while structural failures remain.

Default high-risk zones: auth, permissions, workspace/tenant boundaries, migrations, DB writes, file/artifact writes, pack API endpoints, jobs, cache invalidation, AI output persisted to storage, object resolvers/projections, and deployment/rollback paths.

### Phase 4: Verify Assumptions

Before proposing a fix, verify every assumption the fix depends on.

Typical assumptions to verify:

- the insertion point still contains the expected code
- the target class/function/field actually exists
- the data source contains the shape the plan depends on
- the runtime path being changed is the one actually used
- the dependency can be reloaded hot, or cannot

Use this loop:

```text
FOR EACH assumption:
  1. Ask: "How do I prove this?"
  2. Run the check
  3. Record the result
  4. If the result contradicts the idea, change the plan
```

### Phase 5: Pre-Mortem

Assume the plan has been implemented and failed.

List the most likely failure modes, then check whether you already have evidence ruling them out.

Common failure modes:

1. Wrong insertion point after refactor
2. Schema exists but data is empty or stale
3. Different worker/process/container serves the real traffic
4. Cache or registry survives the change and keeps stale state
5. Validation only covers unit behavior, not propagation to API or UI

If a failure mode is not ruled out, collect more evidence before finishing the plan.

### Phase 6: Write the Plan

Only now write the implementation plan.

For each change block:

- state what it changes
- state which problem ID it resolves
- cite the verified insertion point or dependency
- describe ordering constraints
- describe how to verify the change

For inherited, large, or boundary-crossing work, the first change block should open the modular entrypoint unless the plan explicitly documents and justifies the leaf-only exception.

Good format:

```markdown
### Change 1: Invalidate playbook registry after install
Resolves Problem #2.

- Update `.../capability_install.py` near the post-install activation path so the install flow invalidates the cached playbook registry before returning.
- This insertion point was verified at `...:Lxxx-Lyyy`.
- Do this before the response payload is built so the next request sees fresh registry state.
```

### Phase 7: Audit the Plan

Before delivering:

1. Re-open the most critical cited code ranges.
2. Confirm the plan still matches those lines.
3. Confirm every validation step can actually be run.
4. Remove any sentence that no longer has evidence behind it.

## Validation SOP Rules

The verification section must be operational, not aspirational.

Include:

- the exact command, click path, or API call
- expected result
- what counts as fail
- which problem ID the check proves fixed

Use layered verification when the issue spans multiple layers:

1. Unit or direct function behavior
2. API or service response
3. Consumer path
4. End-to-end symptom check

Do not stop at layer 1 if the original bug was observed at layer 3 or 4.

## Automated Test Plan Rules

Do not write "add tests" as a placeholder.

Specify:

- target test file or module
- exact scenario
- required fixtures or mocks
- expected assertions
- which problem the test prevents from regressing

If automation is not feasible, say why and propose a concrete monitoring or manual regression check instead.

For high-risk changes, include the relevant test layer explicitly: unit for core logic, integration for module/API propagation, regression for previously working behavior, and failure-mode tests for retries, duplicate execution, rollback, or third-party/API failure.

## Backup Rule

If the implementation or verification touches mutable user data, DB rows, generated artifacts, or installed pack state that could be overwritten, put backup instructions at the start of the plan, before any mutation step.

Backup instructions are a backup decision gate, not permission to create a new full backup every time.

Required order:

1. Identify the exact mutation surface: DB rows, installed pack files/state, generated artifacts, app data, logs, or mixed.
2. First look for an existing backup that covers that surface and verify it with the matching verification script.
3. If an existing verified backup covers the risk, reuse it. Do not create another backup.
4. If a new backup is actually required, scope it to the mutation surface. For `scripts/backup_local_runtime.sh`, the default includes DB dumps and a full `/app/data` archive; it is not incremental. Use scoped flags such as `--skip-files` for DB-only protection or `--skip-db` for file-only protection when appropriate.
5. Only run a default/full runtime backup after explicitly stating the expected size/risk and receiving user approval.

Do not bury backup steps inside the testing section.

## Internal Documentation Rule

Persistent local-core internal planning, runtime evidence, operational notes, private paths, DB snapshots, and logs must be written under `mindscape-ai-cloud/docs/internal/local-core/`.

`mindscape-ai-local-core/docs-internal/**` is a legacy read-only quarantine area:

- do not create new internal documents there
- do not edit existing documents there unless the user explicitly asks for legacy recovery
- do not recommend `git add -f`
- do not move the internal file into a tracked public docs path
- if a local-core internal plan/report is requested, write it to `mindscape-ai-cloud/docs/internal/local-core/`
- if a public project record is needed, create a separate sanitized summary that omits internal evidence, local absolute paths, logs, DB rows, queue snapshots, and capability-sensitive operational details

## Prohibited Patterns

### 1. Plan-First Investigation

**WRONG**: Draft the architecture fix, then search for evidence that supports it.

**RIGHT**: Evidence first, plan second.

### 2. Insertion Point From Memory

**WRONG**: "Patch around line 240."

**RIGHT**: Re-open the file and verify the surrounding code before citing the range.

### 3. Schema-As-Data

**WRONG**: "Use field `x` for the rollout gate" when only the model definition was checked.

**RIGHT**: Verify the field is populated in real data or by the relevant writer path.

### 4. Runtime Inference From Source

**WRONG**: "This process restarts on install" because the code contains a reload path.

**RIGHT**: Check role flags, running mode, and the actual install response or runtime logs.

### 5. Validation Without Original Symptom

**WRONG**: "Unit test passes, so the issue is fixed."

**RIGHT**: Reproduce or re-check the original failing path.

### 6. Direct Monolith Editing Without Opening a Seam

**WRONG**: Start by adding new behavior directly into a multi-responsibility file because the insertion point is already known.

**RIGHT**: First create or confirm a modular entrypoint, move the new behavior behind it, and keep the old path as a thin wrapper when feasible.

## Pre-Delivery Checklist

- [ ] Every problem statement cites evidence
- [ ] Priority scoring is included or the ordering rationale is explicit
- [ ] Every proposed insertion point was re-verified
- [ ] Every referenced data source was checked for real contents
- [ ] Every runtime claim has runtime evidence
- [ ] Every "not used / not called" claim uses full-project grep scope
- [ ] Inherited or AI-generated code has a review map before targeted line review
- [ ] Inherited, large, or boundary-crossing work opens with a modular entrypoint, or the leaf-only exception is explicitly justified
- [ ] The plan maps each change to a specific problem ID
- [ ] The verification SOP contains exact commands or UI actions
- [ ] The automated test section names concrete scenarios and assertions
- [ ] Backup steps are included at the start when mutation risk exists
- [ ] Open questions are clearly marked as unknowns, not treated as facts

## Minimal Plan Template

```markdown
# [Title]

## Problems
1. **...** Evidence: E1, E2.
2. **...** Evidence: E3.

## Evidence
- **E1**: `path/to/file.py:L10-L25` shows ...
- **E2**: `curl ...` returned ...

## Proposed Changes
### Change 1: ...
Resolves Problem #1.

- ...

### Change 2: ...
Resolves Problem #2.

- ...

## Verification SOP
1. Run ...
   Pass: ...
   Fail: ...
   Proves: Problem #1

## Automated Test Plan
- Add/extend `...test...`
- Scenario: ...
- Assert: ...
- Prevents regression of Problem #...

## Risks / Open Questions
- ...
```

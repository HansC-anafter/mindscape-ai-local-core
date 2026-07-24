---
name: repo-engineering-assessment
description: Assess an inherited, AI-generated, outsourced, or unfamiliar repository for engineering scope, risk, maintainability, team needs, infrastructure maturity, and rough budget ranges using evidence-backed review maps instead of line-by-line-first review.
---

# Repo Engineering Assessment

<!-- AUTHORIZATION-PRESERVING-CHANGE-CONTROL: REQUIRED -->
## Authorization-Preserving Change Control (Mandatory)

- Preserve the currently authorized capability and requested outcome. Do not reduce limits, concurrency, coverage, priority, routing quality, model or tool choice, features, resource visibility, throughput, or performance unless the user explicitly authorizes that exact downgrade in the current task.
- Treat stability, fairness, load pressure, cost, convenience, and inferred intent as reasons to investigate, never as authorization. If a downgrade appears necessary, stop after read-only diagnosis; show evidence, exact impact, non-downgrade alternatives, and rollback, then wait for explicit approval.
- Do not answer an incident by merely repeating or agreeing with the user's conclusion. Report verified current state, evidence, causal and control path, responsible change when provable, corrective action, validation, residual risk, and clearly label inference or unknowns.
- Apply the full authority at `mindscape-ai-cloud/.agent/skills/authorization-preserving-change-control/SKILL.md`. This compact gate remains binding when that file is unavailable in a packaged runtime.
<!-- /AUTHORIZATION-PRESERVING-CHANGE-CONTROL: REQUIRED -->


Use this skill when asked to evaluate whether a Mindscape repo or capability
pack can be maintained, launched, stabilized, taken over, refactored, staffed,
or budgeted.

## Core Rule

Do not start with full line-by-line review.

First turn the repo into an evidence-backed engineering map:

1. What the system is supposed to do
2. Where the major modules and dataflows are
3. Which areas can cause money, data, security, permissions, or stability damage
4. What tests, deploy paths, logging, rollback, and docs already exist
5. Which parts need targeted line review

Apply `evidence-based-reporting` for factual claims and
`evidence-based-planning` before recommending implementation work.

## Mindscape Scaffold Anchors

Start from the repo's real scaffold, not a generic SaaS checklist.

For `mindscape-ai-cloud` capability packs, inspect:

- `capabilities/<pack>/manifest.yaml`
- `playbooks/specs/`, `playbooks/en/`, `playbooks/zh-TW/`
- `tools/`, `services/`, `api/`, `schema/` or `schemas/`
- `models/`, `database/`, `migrations/`, `jobs/`
- `ui/`, `workflows/`, `evals/`, `tests/`, root `SKILL.md`

Use these repo contracts as evidence anchors:

- `scripts/create_capability.py` for starter scaffold shape; runtime validators win
  when generated code and local-core disagree
- `scripts/package_capability.py` for packageable directories
- `scripts/validate_manifest.py` for manifest/runtime contract checks
- `mindscape-ai-local-core/backend/app/services/runtime_assets_installer.py`
  for install targets
- `mindscape-ai-local-core/backend/app/routes/core/skills.py` for `.agent/skills/<id>/SKILL.md`
  discovery

For installed local-core state, inspect:

- `backend/app/capabilities/<pack>/`
- `web-console/src/app/capabilities/<pack>/`
- `/api/v1/capability-packs/`
- `/api/v1/playbooks/`
- `/api/v1/tools/`

Pack API routes must keep prefix ownership in `manifest.yaml`; installed pack
`api/*.py` routers should not declare `APIRouter(prefix=...)`.

## Assessment Boundaries

Repo assessment can estimate engineering scope and takeover cost. It cannot
prove commercial viability, customer demand, revenue, support cost, legal cost,
or actual production traffic unless external evidence is provided.

Give ranges, not single-point precision, when estimating team, time, or budget.

## Workflow

### 1. Inventory

Collect evidence for:

- languages, frameworks, package managers, build systems
- Mindscape pack surfaces listed above, when present
- app entrypoints, backend routes, services, workers, jobs
- databases, migrations, storage, external services
- APIs, capability UI hosts, auth, permissions, workspace boundaries
- tests, CI/CD, Docker/deploy files, env examples, docs

### 2. Review Map

Produce a compact table:

| Module | Responsibility | Risk | Evidence | Line Review | Test Status |
|---|---|---|---|---|---|
| `...` | `...` | High/Med/Low | file/command refs | yes/partial/no | present/missing/unknown |

Risk defaults:

- High: auth, permissions, workspace/tenant boundaries, migrations, DB writes,
  file/artifact writes, pack API endpoints, jobs, AI execution, persisted AI
  output, object resolvers/projections, deploy/rollback
- Medium: capability UI hosts, reporting, cache, notifications, third-party sync
- Low: static copy, visual styling, isolated display components

### 3. Targeted Review

Only after the map exists, review high-risk areas line by line.

Check for:

- wrong layer placement or bypassed framework conventions
- manifest/runtime mismatches, including unsupported UI surfaces
- `tool_slot` references that do not resolve to registered pack tools
- pack API routers that duplicate the manifest-owned prefix
- missing validation, authorization, idempotency, rollback, or error handling
- race conditions, duplicate execution, cache staleness, infinite loops
- schema fields assumed to contain data but never populated
- helper code that exists but is not connected to the real path
- duplicated custom logic where the framework already has a mechanism

### 4. Verification Surface

Assess whether important behavior can be proven with:

- unit tests for core rules
- integration tests for API/module propagation
- regression tests for known workflows
- failure-mode tests for retries, third-party failure, duplicate jobs, rollback
- runtime smoke checks for the original user-facing path

Missing tests increase takeover risk even when the app appears to run.

### 5. Operations Surface

Check whether production operation is supportable:

- reproducible setup
- environment/config documentation
- migrations and seed data
- CI/CD or release procedure
- staging or preview environment
- logs, error tracking, monitoring
- backup/restore
- rollback/backout path
- secrets management

### 6. Estimate

Estimate by engineering responsibility, not lines of code.

Use ranges such as:

- Small cleanup / launch hardening
- Formal takeover and stabilization
- Production SaaS hardening
- Platform refactor or rewrite candidate

For each range, state:

- why the repo falls there
- primary risk drivers
- team shape needed
- first 30/60/90 day focus
- assumptions and unknowns

## Output Shape

Use this order:

1. Executive assessment
2. Evidence collected
3. Review map
4. High-risk findings
5. Test and verification gaps
6. Operations and deploy gaps
7. Takeover/refactor options
8. Team, time, and budget ranges
9. Unknowns that require more evidence

## Prohibited Shortcuts

- Do not estimate from LOC alone.
- Do not use generic SaaS categories until the Mindscape scaffold surfaces above
  have been mapped.
- Do not declare "rewrite" before mapping modules, risk, and testability.
- Do not declare "production ready" without deploy, monitoring, rollback, and
  original-path smoke evidence.
- Do not say a feature exists because a helper/component exists; verify the real
  caller, route, hook, job, or UI path.
- Do not average-review every file equally; concentrate line review on high-risk
  zones after the review map is built.

---
name: evidence-based-planning
description: Formal workflow for writing implementation plans. Enforces evidence-first discipline from problem definition through plan verification, while keeping plans grounded in user workflows and product narrative.
---

# Evidence-Based Planning

## Core Rule

**No implementation plan may be written until all problems are defined with evidence, and every proposed change has its insertion point verified against actual code.**

Violation of this rule produces plans with wrong line numbers, invalid data source assumptions, and designs that reference nonexistent APIs.

## Product Narrative Guardrail

Evidence-first does **not** mean engineering-only language.

For any implementation plan that defines or changes a capability pack, workflow, feature surface, automation, or user-visible behavior, the plan MUST begin with a plain-language product framing section **before** the technical problem register.

If a plan cannot explain itself without leading with pack names, APIs, or runtime components, the plan is not ready.

### Required opening block for product-facing plans

Before Phase 2, include a plain-language section that answers:

1. What real-world problem this pack/feature solves
2. How it solves that problem at the workflow level
3. What using it should feel like for the operator or end user
4. What the standard user journey / operating logic looks like
5. What P0 does **not** promise
6. What artifacts, approvals, or traceability the user should be left with

### Required companion block

Also include a `True / False` productization checklist that can be used to detect drift early.

Rules:

- Each checklist item must be a clear product or workflow statement, not a vague aspiration
- Each item must say what `TRUE` means and what `FALSE` means
- Any `FALSE` item should be treated as a design warning, not as a cosmetic documentation issue
- The checklist must be understandable to a product/operator stakeholder without repo-specific context

---

## Mandatory Phases

### Phase 1: Evidence Collection

Collect evidence for every relevant code path BEFORE defining any problem.

```
FOR EACH component under investigation:
  1. Read the actual code (view_file with exact line ranges)
  2. Verify runtime state where applicable (docker exec, DB query, log grep)
  3. Record evidence with file path + line number
  4. Do NOT write any conclusions yet
```

**Applies**: `evidence-based-reporting` skill rules. Every claim needs evidence.

### Phase 1.5: Historical Regression Analysis (Git History)

Before defining the current problem, review the git history (`git log -p`) of the component to understand past fixes.

```
FOR EACH previous fix related to the component:
  1. What was the exact code change?
  2. Why did the author think it would work?
  3. Why did it ultimately fail (creating the current problem)?
  4. How does the NEW proposed approach structurally avoid the failure mode of the past fixes?
```

This prevents repeating past mistakes (e.g., swapping one unreliable API for another) by formally acknowledging why previous attempts failed.

### Phase 2: Problem Definition + Severity Scoring

Write a numbered list of concrete problems, each referencing evidence items.

```
FORMAT:
  1. **[Problem title]**: [one-line description] (E1, E2)
  2. **[Problem title]**: [one-line description] (E3, E5)
```

Rules:
- Each problem must cite at least one evidence item
- No problem may be inferred without code or runtime evidence
- Problem list goes at the TOP of the analysis report
- Each problem should make the product or operator impact legible, not just the technical gap
- For pack/productization plans, at least one problem must describe what breaks in the user flow if the issue is left unresolved

**FMEA-lite scoring** — prioritize which problems to fix first:

```
FOR EACH problem:
  Severity  (1-5): How bad if this causes a production incident?
  Detection (1-5): How hard is it to catch before production?
  Priority = Severity × Detection (higher = fix first)
```

| Problem | Severity | Detection | Priority |
|---------|----------|-----------|----------|
| Pipeline 零校驗 | 5 | 5 | 25 |
| Fallback 吐全量 | 4 | 3 | 12 |
| RAG 不索引 playbook | 3 | 2 | 6 |

This prevents fixing low-impact issues while critical gaps remain open.

### Phase 3: Assumption Verification (CoVe)

Before writing any fix, verify every assumption using Chain-of-Verification:

```
FOR EACH proposed change:
  1. Generate verification question:
     "How would I prove [assumption] is correct?"
  2. Execute the verification (view_file, grep, runtime query)
  3. Record the answer with evidence
  4. If answer contradicts expectation → update understanding, do NOT ignore
```

Assumption verification table:

| Assumption Type | Verification Question | Method |
|---|---|---|
| "Insert code at line N" | "Do lines N-1 and N+1 match what I expect?" | `view_file` that range |
| "Data source X contains Y" | "What does X actually contain?" | Read indexing/writing code, or query data |
| "Model has field X with data" | "Is field X populated, or just defined?" | Grep data files + check writer code |
| "Function X is not called" | "Does a full-project grep find callers?" | Grep full project, report scope |
| "Object has attribute X" | "Does the class definition include X?" | Grep model/class definition |
| "N items at runtime" | "What does the count query return?" | Run count in actual environment |

### Phase 3.5: Pre-Mortem

After verifying assumptions, apply adversarial thinking:

```
ASSUME the plan has been implemented and has FAILED.
List the 3 most likely failure modes:

  1. Data assumption wrong — a field, index, or source doesn't contain
     what the plan assumes (e.g., schema ≠ data)
  2. Insertion point shifted — code was refactored, line numbers moved,
     or method signature changed since evidence was collected
  3. Runtime dependency missing — service not running, table not created,
     environment variable not set

FOR EACH failure mode:
  - Is there evidence ruling it out?
  - If not: run the verification now
```

### Phase 4: Plan Writing

Write the implementation plan with verified citations only.

Rules:
- Every `[file.py:LN]` citation must have been verified in Phase 3
- Every data source referenced must have been verified in Phase 3
- Every model attribute must have been confirmed to exist
- Group changes by dependency order (independent first)
- For product-facing work, begin the plan with the required plain-language product framing and `True / False` checklist before the technical implementation series
- **Traceability**: Every implementation block MUST explicitly state which Phase 2 Problem ID it resolves (e.g., `Resolves Problem #2`).
- Every implementation block should also state the user-facing behavior, operator step, or product outcome it enables
- **Provide concrete code diffs OR precise code replacement logic** for all critical modifications at verified insertion points
- If the plan depends on an unresolved host/kernel seam, specify the downgrade or handoff path explicitly instead of assuming a future API will exist
- Include verification commands for each phase

### Phase 5: Citation Audit (CoVe Final Pass)

After writing the plan, run a final verification pass:

```
FOR EACH file referenced in the plan:
  1. Pick the most critical citation (insertion point or data dependency)
  2. view_file that exact line range
  3. Confirm the content matches what the plan describes
  4. If any mismatch: STOP and correct before delivering
```

### Phase 6: Validation SOP (Standard Operating Procedure)

Define a rigorous step-by-step SOP that connects the original problem to the fix and how to verify it. 

Rules:
- Give a clear narrative: "How did we diagnose this (Phase 1-3), how did we fix this (Phase 4), and how do we verify it now?"
- List specific scenarios (e.g., "sunny day", "error case").
- Provide the exact verification steps (Where to click, what `curl` or SQL command to run).
- Define explicitly what constitutes a "Pass" and a "Fail" for the verification, mapping back to the original Problem ID.
- For product-facing plans, the first validation scenario should be an operator or user journey, not just an API-level proof
- If approval, handoff, publish, measurement, or writeback are part of the story, the SOP must verify artifact continuity across those steps
- **🚨 DATA BACKUP WARNING**: If the verification SOP requires modifying, deleting, or overwriting data (e.g., database records, static files), you MUST instruct the user to **perform a data backup BEFORE making any code changes**. This backup step must be placed at the VERY BEGINNING of the Implementation Plan (Phase 4), NOT buried inside the Testing SOP (Phase 6).

  > **Standard Backup Procedure:**
  > - All backups MUST be saved to the local-core `.gitignore`'d directory: `data/backups/`
  > - For PostgreSQL database backups, use this exact command:
  >   ```bash
  >   docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_test_$(date +%Y%m%d_%H%M%S).sql
  >   ```

### Phase 7: Evaluation & Automated Testing SOP

Propose an exact automated testing strategy that protects the specific logic fixed in this plan.

Rules:
- Do not just write "Write a test". You must propose the **exact test cases** (Input, Mock setup, Expected Output).
- Explain how this automated test specifically prevents the Problem IDs identified in Phase 2 from recurring.
- If an automated test is not feasible, explain why and propose a monitoring metric or dashboard.

---

## Prohibited Patterns

### 1. Plan Before Evidence

**WRONG**: Write an implementation plan, then go back and verify the claims.

**RIGHT**: Phases 1→2→3→3.5→4→5 in strict order. Never write Phase 4 before completing Phase 3.5.

### 2. Assumed Data Source Scope

**WRONG**: "Validation will use data from index X." (never checked what X contains)

**RIGHT**: Before referencing any data source in a design, verify what it actually contains, whether the format matches, and whether the scope covers your full requirement.

### 3. Schema Field as Available Data

**WRONG**: "Model has field `X` — use it for validation." (field defined but never populated)

**RIGHT**: Check whether the field has actual data. Default-valued fields (`default_factory=list`, `default=None`) are assumed empty until proven otherwise.

### 4. Unverified Insertion Point

**WRONG**: "Insert after line 108." (line 108 contains completely different code)

**RIGHT**: `view_file` the exact insertion point and confirm the surrounding context matches.

### 5. Skipped Pre-Mortem

**WRONG**: Plan passes all forward verification, but fails in production because a runtime dependency was never checked.

**RIGHT**: Always run Phase 3.5. Assume failure, enumerate modes, verify each one is ruled out.

### 6. Abstract Stack-First Framing

**WRONG**: Start with "Add orchestration service around A/B/C" without first explaining the operator workflow.

**RIGHT**: Start with the user journey or operator flow, then map that flow onto the actual packs, APIs, services, and artifacts.

### 7. Technical Closure Without Product Closure

**WRONG**: "Preview works" while approval, handoff, writeback, or follow-on measurement are undefined.

**RIGHT**: State clearly where the product loop ends in this phase, what handoff artifact remains, and what later phase closes the rest of the loop.

### 8. Runtime-First Product Definition

**WRONG**: Define the feature primarily as an integration with model/runtime/provider X.

**RIGHT**: Define the feature primarily as a user-facing capability; treat models and runtimes as replaceable execution backends unless the product requirement truly depends on one specific runtime.

---

## Pre-Delivery Checklist

Before delivering any implementation plan:

- [ ] Every problem cites evidence items
- [ ] Problems are severity-scored and ordered by priority
- [ ] For product-facing work, the plan opens with a plain-language product/UX framing section
- [ ] For product-facing work, the plan includes a `True / False` productization checklist
- [ ] Every insertion point has been `view_file`'d and confirmed
- [ ] Every data source dependency has been verified for content and format
- [ ] Every model attribute access has been confirmed to exist
- [ ] Runtime quantities cite actual command output, not code inference
- [ ] Negation claims use full-project grep with scope reported
- [ ] Pre-mortem failure modes have been enumerated and ruled out
- [ ] Changes are ordered by dependency (independent first)
- [ ] Every implementation block traces back to a specific Problem ID from Phase 2
- [ ] Every implementation block makes the user-facing outcome or operator step clear
- [ ] Concrete code diffs or explicit replacement logic are provided for key changes
- [ ] Verification commands are included for each phase
- [ ] A Validation Checklist (Phase 6) with explicit pass/fail criteria and commands is included
- [ ] The plan explicitly states what P0 does not promise and where the product loop ends for this phase
- [ ] 🚨 Data backup instructions are placed at the very start of Implementation (if testing modifies data)
- [ ] An Evaluation/Automated Testing section (Phase 7) is included to prevent regression

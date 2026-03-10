---
name: evidence-based-planning
description: Formal workflow for writing implementation plans. Enforces evidence-first discipline from problem definition through plan verification.
---

# Evidence-Based Planning

## Core Rule

**No implementation plan may be written until all problems are defined with evidence, and every proposed change has its insertion point verified against actual code.**

Violation of this rule produces plans with wrong line numbers, invalid data source assumptions, and designs that reference nonexistent APIs.

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

---

## Pre-Delivery Checklist

Before delivering any implementation plan:

- [ ] Every problem cites evidence items
- [ ] Problems are severity-scored and ordered by priority
- [ ] Every insertion point has been `view_file`'d and confirmed
- [ ] Every data source dependency has been verified for content and format
- [ ] Every model attribute access has been confirmed to exist
- [ ] Runtime quantities cite actual command output, not code inference
- [ ] Negation claims use full-project grep with scope reported
- [ ] Pre-mortem failure modes have been enumerated and ruled out
- [ ] Changes are ordered by dependency (independent first)
- [ ] Verification commands are included for each phase

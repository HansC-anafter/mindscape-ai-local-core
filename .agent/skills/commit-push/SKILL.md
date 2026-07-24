---
name: commit-push
description: Batch-commit all outstanding changes by component, using Conventional Commits. Push is a SEPARATE action — only push when the user explicitly says "push".
---

# Commit & Push (local-core)

<!-- AUTHORIZATION-PRESERVING-CHANGE-CONTROL: REQUIRED -->
## Authorization-Preserving Change Control (Mandatory)

- Preserve the currently authorized capability and requested outcome. Do not reduce limits, concurrency, coverage, priority, routing quality, model or tool choice, features, resource visibility, throughput, or performance unless the user explicitly authorizes that exact downgrade in the current task.
- Treat stability, fairness, load pressure, cost, convenience, and inferred intent as reasons to investigate, never as authorization. If a downgrade appears necessary, stop after read-only diagnosis; show evidence, exact impact, non-downgrade alternatives, and rollback, then wait for explicit approval.
- Do not answer an incident by merely repeating or agreeing with the user's conclusion. Report verified current state, evidence, causal and control path, responsible change when provable, corrective action, validation, residual risk, and clearly label inference or unknowns.
- Apply the full authority at `mindscape-ai-cloud/.agent/skills/authorization-preserving-change-control/SKILL.md`. This compact gate remains binding when that file is unavailable in a packaged runtime.
<!-- /AUTHORIZATION-PRESERVING-CHANGE-CONTROL: REQUIRED -->


> **Important: Commit and Push are INDEPENDENT operations.**
> - User says "提交" / "commit" → **Only commit** (Steps 0–2)
> - User says "推送" / "push" → **Only push** (Step 3)
> - User says "提交並推送" / "commit and push" → Both (Steps 0–3)

> Pre-commit hook: `scripts/git-hooks/pre-commit.template` (50-file threshold)

---

## Step 0: Pre-flight Checks

// turbo
```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
echo "--- Branch ---"
git branch --show-current
echo "--- Dirty .env check ---"
git status --porcelain | grep -E '^\?\?.*\.env$|^ ?M.*\.env$' || echo "OK: no .env staged"
echo "--- Staged file count ---"
git diff --cached --name-only | wc -l | tr -d ' '
```

**Gate rules** (abort if any fail):
- Current branch is NOT `main` or `develop` (create `feature/*` or `fix/*` first)
- No `.env` file in changes
- No `node_modules/` in changes

---

## Step 1: Scan & Classify Changes

// turbo
```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
git status --porcelain
```

Classify each changed file into one of these **component groups** (in commit order):

| Priority | Component | Path prefix | Commit scope |
|----------|-----------|-------------|--------------|
| 1 | DB Models | `backend/app/models/` | `models` |
| 2 | DB Migrations | `backend/alembic_migrations/` | `migrations` |
| 3 | Core Services | `backend/app/services/` | `services` |
| 4 | Core Routes | `backend/app/routes/` | `routes` |
| 5 | Features | `backend/app/features/` | `features` |
| 6 | Middleware/Core | `backend/app/middleware/`, `backend/app/core/` | `core` |
| 7 | Backend Other | `backend/` (remaining) | `backend` |
| 8 | Frontend | `web-console/` | `web-console` |
| 9 | Packages | `packages/` | `packages` |
| 10 | Scripts | `scripts/` | `scripts` |
| 11 | Internal Docs | Use `mindscape-ai-cloud/docs/internal/local-core/`; never local-core `docs-internal/` | n/a |
| 12 | Public Docs | `docs/` | `docs` |
| 13 | Config | root configs (`docker-compose*`, `*.yml`, `*.json`, `*.toml`) | `config` |

**Document language distinction** (嚴格區分):
- local-core internal docs → write in `mindscape-ai-cloud/docs/internal/local-core/`, **繁體中文**
- local-core `docs-internal/` → legacy read-only quarantine; never create, edit, or commit new internal docs there
- `docs/` → **English** (公開開源文件，scope: `docs`)

**Exclusions** (never commit these):
- `backend/app/capabilities/` — installed packs, managed by `.mindpack`
- `*.mindpack` — pack archives
- `docker-compose.override.yml` — local dev only
- `data/` — local runtime data
- `node_modules/` — dependencies
- `.env` — secrets
- `__pycache__/` — Python cache
- `docs-internal/` — legacy read-only quarantine

---

## Step 1.5: Code Comment Compliance Check

Before committing, verify changed files comply with comment rules:

**Language rules:**
- Allowed: Code comments & docstrings: **English** (i18n base)
- Allowed: Internal docs in cloud (`mindscape-ai-cloud/docs/internal/local-core/`): **繁體中文**
- Forbidden: local-core `docs-internal/`: legacy read-only quarantine; no new writes or commits
- Allowed: Public docs (`docs/`): **English** (open-source facing)
- Forbidden: Never mix languages within the same comment block
- Forbidden: Never use 簡體中文 (this is a 繁體中文 project)

**Forbidden in code comments** (violating = 死罪):

| Forbidden | Use instead |
|-------------|---------------|
| Emojis | Technical descriptions |
| Timeline (`M4 Week 11`, `Day 1-3`, `Phase 2`) | Explain "why" not "when" |
| Personal IDs (`工程師 B 實現`) | Technical decisions |
| Doc versions (`參考: XXX_PLAN.md v3.5`) | Type annotations |
| Creation timestamps | `TODO: <description>` (no timeline) |
| Implementation step logs (`Step 1:...`) | Functional descriptions |

**Python docstring format** (from developer guide):
```python
# Correct: English docstrings
def create_mindscape(name: str, description: str) -> Mindscape:
    """
    Create a new Mindscape

    Args:
        name: Mindscape name
        description: Mindscape description

    Returns:
        Created Mindscape object
    """
```

---

## Step 2: Batch Commit

For **each non-empty component group**, run:

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
git add <file1> <file2> ...
git commit -m "<type>(<scope>): <subject>"
```

**Commit message rules** (Conventional Commits):
- `feat(<scope>):` — new functionality
- `fix(<scope>):` — bug fixes
- `refactor(<scope>):` — restructuring without behavior change
- `docs(<scope>):` — documentation only; local-core internal docs must be committed from the cloud repo under `docs/internal/local-core/`
- `chore(<scope>):` — configs, scripts, tooling
- `style(<scope>):` — formatting only
- `test(<scope>):` — test files

**Batching**: if a single group has > 50 files, split into sub-batches of ≤ 50.

> **NEVER** use `git add .` — always list files explicitly.

**🛑 STOP HERE** unless the user explicitly requested push.

---

## Step 3: Push (ONLY when user explicitly requests)

> **This step is ONLY executed when the user explicitly says "push" or "推送".**
> If the user only said "commit" or "提交", DO NOT execute this step.

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
git push origin $(git branch --show-current)
```

If the remote branch does not exist yet:

```bash
git push -u origin $(git branch --show-current)
```

---

## Step 4: Post-Action Verify

// turbo
```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
echo "--- Remaining changes ---"
git status --porcelain
echo "--- Last 5 commits ---"
git log --oneline -5
echo "--- Unpushed commits ---"
git log --oneline origin/$(git branch --show-current)..HEAD 2>/dev/null | wc -l | tr -d ' '
```

**After commit only**: zero remaining changes, unpushed count > 0 is expected.
**After push**: zero remaining changes, zero unpushed commits.

---

## FATAL Rules

- **NEVER** `git add .` — always specify files explicitly
- **NEVER** commit `.env` files
- **NEVER** commit `backend/app/capabilities/` (installed packs)
- **NEVER** commit `*.mindpack` archive files
- **NEVER** commit `docker-compose.override.yml`
- **NEVER** commit directly to `main` or `develop`
- **NEVER** commit `node_modules/` or `data/`
- **NEVER** push unless the user explicitly requests it
- **ALWAYS** use Conventional Commits format
- **ALWAYS** use English commit messages
- **ALWAYS** use English for code comments and docstrings
- **ALWAYS** use 繁體中文 for cloud internal docs, English for local-core `docs/`
- **ALWAYS** verify code comments are free of emojis, timelines, and personal IDs before committing

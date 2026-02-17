---
name: mindscape-dev-guide
description: Enforce Mindscape AI local-core development rules - architecture boundaries, code style, Git workflow, and documentation conventions.
---

# Mindscape AI Local-Core Developer Guide (Agent Skill)

> Source of truth: `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`
> Internal docs language: **Traditional Chinese (zh-TW)**
> Code / comments / logger messages language: **English only**

---

## 1. Architecture Boundaries (FATAL violations)

### 1.1 Local-Core Is a Pure Runtime

local-core is a **runtime environment only**. It provides Kernel and Core Primitive APIs (`/artifacts`, `/executions`, `/workspaces`, `/playbooks`, `/config`, etc.).

**FORBIDDEN in local-core:**

- Platform-specific business APIs or UI components
- Platform-specific SDK methods
- Scheduling, publishing, content-status management logic
- Any tenant-specific business logic in core routes

### 1.2 No Cross-Repo File System Access

**NEVER** read external repo file systems from local-core code:

```python
# FATAL: direct filesystem read via env var
remote = os.getenv("MINDSCAPE_REMOTE_CAPABILITIES_DIR")
load_capabilities(Path(remote))  # FORBIDDEN

# FATAL: hardcoded external path
external = Path("../other-repo/capabilities")  # FORBIDDEN
```

### 1.3 No Raw Capability Source in local-core

Never commit raw capability source code directly into `local-core/backend/app/capabilities/`. Capabilities are installed only via `.mindpack` packages through the API (`POST /api/v1/capability-packs/install-from-file`).

### 1.4 Hotspots to Audit

Before committing changes to these files, verify no cross-repo reads:

- `backend/app/services/playbook_loaders/json_loader.py`
- `backend/app/services/tool_list_service.py`
- `backend/app/main.py`
- `backend/app/capabilities/registry.py`

---

## 2. Five Death-Line Rules

> Violating ANY of these = immediate revert, no exceptions.

| # | Rule | Key constraint |
| --- | ---- | ---- |
| 1 | No hardcoded secrets | All sensitive info from env vars; `.env` in `.gitignore`; never log secrets |
| 2 | Local-first principle | Core features must work offline; optional features via adapter pattern; no cloud/tenant hardcoding in core routes |
| 3 | Data integrity | All schema changes via migration scripts; never drop tables/columns without migration; backward compatible |
| 4 | API compatibility | Never remove endpoints; never break request/response format; provide version migration path |
| 5 | Tested code only | No broken builds; no regressions; basic tests must pass before commit |

---

## 3. Code Style Rules

### 3.1 Language Rules (MANDATORY)

| Context | Language |
| ---- | ---- |
| Code comments | English only |
| Docstrings | English only |
| Logger messages | English only, no emoji |
| Variable / function names | English (snake_case Python, camelCase TS) |
| Internal docs (`docs-internal/`) | Traditional Chinese (zh-TW) |
| Commit messages | English, Conventional Commits |

### 3.2 Forbidden in Code Comments

- **No Chinese** in `.py` / `.ts` / `.tsx` / `.js` files
- **No emoji** in code comments or logger messages
- **No implementation-step notes** (e.g. `# Step 1: ...`, `# DONE: ...`)
- **No non-functional descriptions**

### 3.3 Python (Backend)

- Follow **PEP 8** strictly (snake_case, type hints)
- Write English docstrings (Args/Returns format)

```python
def get_workspace_by_id(workspace_id: int) -> Optional[Workspace]:
    """
    Get a workspace by its primary key.

    Args:
        workspace_id: Workspace primary key

    Returns:
        Workspace object or None if not found
    """
```

### 3.4 TypeScript (Frontend)

- TypeScript interfaces for all data shapes
- Function components only (no class components)
- Next.js App Router conventions
- Server Components by default; `"use client"` only when needed

---

## 4. Git Workflow

### 4.1 Branch Strategy

| Branch | Purpose |
| ---- | ---- |
| `main` | Production; receives merges from `develop` only |
| `develop` | Development trunk |
| `feature/*` | New features |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation updates |

### 4.2 Conventional Commits

```
<type>(<scope>): <subject>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

```bash
# Correct
git commit -m "feat(core): add workspace management API"

# WRONG
git commit -m "update"
git commit -m "fix bug"
```

### 4.3 Commit Hygiene

- **NEVER** use `git add .` -- always specify files explicitly
- **NEVER** commit `.env` files
- **NEVER** bypass Git to modify production/VM directly

### 4.4 PR Checklist

- [ ] English comments, no emoji, no Chinese in code
- [ ] Basic tests pass
- [ ] No secrets leaked
- [ ] No business logic in core routes
- [ ] Local-first principle maintained
- [ ] Migration script for any DB schema change

---

## 5. Environment Variable Management

```bash
cp env.example .env      # Copy template
# Edit .env with required keys
```

```python
# Correct
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is required")

# FATAL
api_key = "sk-1234567890abcdef..."   # Hardcoded secret
```

Sensitive items: API Keys, DB passwords, JWT secrets, OAuth client secrets, auth tokens.

---

## 6. Development Environment

### 6.1 Docker-Only Workflow

All development runs inside Docker containers. Direct Python/Node execution on host is forbidden (except host-side bridge scripts).

```bash
# Correct
docker compose up -d
docker compose exec backend bash
docker compose logs -f backend

# FATAL
python backend/app/main.py
npm run dev   # unless inside container
```

### 6.2 Service Ports

| Service | Port (container) | Port (host) |
| ---- | ---- | ---- |
| Backend (FastAPI) | 8000 | 8200 |
| Frontend (Next.js) | 3000 | 3001 |
| PostgreSQL | 5432 | 5432 |

### 6.3 Bridge Scripts (Host-Side Exception)

Some scripts run on the **host machine**:

- `scripts/start_cli_bridge.sh`
- `scripts/start_ws_bridge.sh`
- `scripts/gemini_cli_runtime_bridge.py`

These connect to the backend API at `http://localhost:8200`.

---

## 7. Project Structure (local-core Only)

```
mindscape-ai-local-core/
├── backend/
│   └── app/
│       ├── main.py                 # FastAPI entry point
│       ├── routes/core/            # Layer 0 Kernel + Layer 1 Core Primitives
│       ├── features/               # Layer 2 Domain/UX (pluggable)
│       ├── core/ports/             # Port interface definitions
│       ├── adapters/               # Adapter implementations
│       ├── services/               # Business logic
│       ├── models/                 # Database models
│       ├── middleware/             # Auth, logging
│       ├── capabilities/           # Installed packs (via .mindpack only)
│       └── migrations/             # Alembic DB migrations
├── web-console/                    # Next.js frontend
│   └── src/
│       ├── app/                    # App Router pages
│       ├── components/             # React components
│       └── lib/                    # Utilities
├── scripts/                        # Shell/Python utilities
├── docs-internal/                  # Internal docs (zh-TW)
├── docker-compose.yml
├── env.example
└── data/                           # Local data (gitignored)
```

### Routes Classification

| Layer | Location | Nature |
| ---- | ---- | ---- |
| Layer 0: Kernel | `routes/core/` | Hardcoded, never pluggable |
| Layer 1: Core Primitives | `routes/core/` | Manager hardcoded, content pluggable |
| Layer 2: Domain/UX | `features/` | Fully pluggable |

---

## 8. Documentation Conventions

### 8.1 Internal Documentation

- Location: `docs-internal/`
- Language: **Traditional Chinese (zh-TW)**
- Implementation records: `docs-internal/implementation/{feature}-{date}.md`
- Architecture decisions: `docs-internal/architecture/change-request-{topic}-{date}.md`

### 8.2 Implementation Document Contents

1. Background / motivation
2. Architecture overview (components, data flow)
3. Files changed (absolute paths, line numbers)
4. Known issues / blockers
5. Verification results
6. Remaining TODOs

### 8.3 Cross-Referencing

After completing a feature, add links to:
- `DEVELOPER_GUIDE_MINDSCAPE_AI.md` section "Related Documents"
- Relevant change request documents

---

## 9. Authentication (local-core scope)

### 9.1 GCA Auth (Google Cloud Access)

- Backend endpoint: `GET /api/v1/auth/cli-token` (auto-refreshes expired tokens)
- Bridge script fetches fresh token before each CLI invocation
- Env vars: `GOOGLE_GENAI_USE_GCA=true`, `GOOGLE_CLOUD_ACCESS_TOKEN=<token>`

### 9.2 Fernet Encryption

OAuth tokens encrypted at rest using Fernet. Key persisted via Docker volume (`./data/secrets:/root/.mindscape:rw`).

---

## Quick Reference: Pre-Commit Checklist

```
[ ] No Chinese in code comments / logger messages
[ ] No emoji in code / logs
[ ] No hardcoded secrets
[ ] No business logic in core routes
[ ] No cross-repo filesystem access
[ ] No raw capability source in local-core
[ ] No `git add .` (explicit file names only)
[ ] .env NOT committed
[ ] Type hints on all Python functions
[ ] English docstrings
[ ] Conventional Commits message format
[ ] All changes via Git (never direct VM modification)
[ ] Migration script for any DB schema change
```

# Installation Guide

This guide describes the supported installation paths for Mindscape AI Local Core.

## Recommended Installation

Use Docker Compose for normal setup. Use local backend or web console processes when actively developing those services.

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
./scripts/start.sh
```

On Windows PowerShell, use `.\scripts\start.ps1`. The launchers automatically bootstrap internal database secrets; do not add `POSTGRES_VECTOR_RUNTIME_PASSWORD` to `.env`.

Then open:

- `http://localhost:8300` for the web console
- `http://localhost:8200/docs` for API docs
- `http://localhost:8200/healthz` for liveness

See [Docker Deployment Guide](./docker.md) for service details, profiles, ports, data paths, and backups.

## Update an Existing Installation

Use the repository's canonical startup helper after pulling a fast-forward update. On Windows PowerShell:

```powershell
git pull --ff-only
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

This path loads the DPAPI-protected internal runtime secret before Compose evaluates the service configuration. Use `.\scripts\compose.ps1 restart <service>` for a later service-only restart. Do not replace either command with bare `docker compose`, and do not add `POSTGRES_VECTOR_RUNTIME_PASSWORD` to `.env`.

For macOS and Linux update commands, see [Update an Existing Installation](./docker.md#update-an-existing-installation).

## Environment File

The system can start with provider API keys unset. AI features that require external LLM providers become available after configuration.

Create `.env` from the example when needed:

```bash
cp .env.example .env
```

Set only the values you need. Common values include:

```env
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
LOCAL_AUTH_SECRET=dev-secret-key-change-in-production
TZ=UTC
```

Database defaults and the internal vector runtime credential are managed by the startup path. Override public database names or host directories only when required; do not manage the internal vector credential in `.env`.

## Advanced Local Process Mode

Manual process mode is for developers. It requires Python, Node.js, PostgreSQL, Redis, and the same environment contracts used by Docker Compose.

Backend requirements:

- Python 3.11 recommended
- `backend/requirements.txt`
- PostgreSQL reachable through `DATABASE_URL_CORE` and `DATABASE_URL_VECTOR`
- Redis reachable through `REDIS_HOST` and `REDIS_PORT`, or intentionally disabled in local configuration
- `PYTHONPATH` that includes the repository root and `backend`

Example backend command from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
PYTHONPATH="$PWD:$PWD/backend" HOST=0.0.0.0 PORT=8200 uvicorn backend.app.main:app --reload
```

On Windows PowerShell, set equivalent environment variables before starting `uvicorn`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
$env:PYTHONPATH="$PWD;$PWD\backend"
$env:HOST="0.0.0.0"
$env:PORT="8200"
uvicorn backend.app.main:app --reload
```

Frontend requirements:

- Node.js 18 or another version compatible with the web console dependency set
- pnpm through Corepack, matching the Docker frontend build and workspace lockfile

Run dependency installation from the repository root because `web-console` is part of the pnpm workspace:

```bash
corepack enable
pnpm install
cd web-console
pnpm run dev -- -H 0.0.0.0
```

The standalone frontend development server defaults to port `3000`. The Docker stack exposes the web console on host port `8300`.

## What Not To Install Manually

Keep capability internals, generated runtime bundles, local data, credentials, and ignored implementation paths in their runtime or owner-managed locations. Installed capabilities and generated artifacts are runtime material outside the Local Core source installation steps.

# Docker Deployment Guide

Docker Compose is the supported startup path for Mindscape AI Local Core.

## Prerequisites

- Docker with Docker Compose v2
- Git
- At least 8 GB of memory available to Docker for the default service set
- Enough disk space for container images, PostgreSQL data, model caches, and generated local data

LLM provider keys are optional for startup. Without them, the system can start, but AI features that need external LLM providers will be unavailable until configured.

## Start

Clone the repository and start the default Docker services:

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
docker compose up -d
```

Linux and macOS users can also use the startup helper:

```bash
./scripts/start.sh
```

Windows PowerShell users can use:

```powershell
.\scripts\start.ps1
```

The helper scripts check Docker availability and can start host-side companion processes. The direct `docker compose up -d` path is the simplest container-only startup path.

## Startup Modes

Direct Compose starts the default container set only:

```bash
docker compose up -d
```

The macOS and Linux helper checks Docker, prepares repository-defined host companions when available, and then starts Compose with the `control-plane` profile:

```bash
./scripts/start.sh
```

The Windows helper checks Docker, prepares Windows host companions when available, and then starts the default Compose stack:

```powershell
.\scripts\start.ps1
```

Use direct Compose for a container-only smoke test. Use a helper when you need the local host companions that are part of this repository's startup flow. Do not add capability internals, generated runtime bundles, ignored paths, local data, or credentials to public setup steps.

## Access

Default local endpoints:

- Web console: `http://localhost:8300`
- Backend API: `http://localhost:8200`
- API docs: `http://localhost:8200/docs`
- Backend liveness: `http://localhost:8200/healthz`
- Backend health details: `http://localhost:8200/health`

## Services

The default Compose stack includes:

- `backend`: FastAPI backend on host port `8200`
- `frontend`: Next.js web console on host port `8300`
- `postgres`: PostgreSQL with pgvector on host port `5433`
- `redis`: Redis on host port `6379`
- `runner-default`, `runner-browser`, and `runner-vision`: local task runner workers
- `media-proxy`: media proxy on host port `8202`
- `xtts-service`: local TTS sidecar on host port `8020`
- `whisper-service`: local Whisper sidecar on host port `8006`

Optional profiles:

- `control-plane`: starts `backend-control` on host port `8220` by default
- `ocr`: starts `ocr-service` on host port `8001`

Examples:

```bash
docker compose --profile control-plane up -d
docker compose --profile ocr up -d
```

## Configuration

The repository includes `.env.example`. Copy it to `.env` when you need persistent local configuration:

```bash
cp .env.example .env
```

Useful settings include:

- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` for external LLM providers
- `LOCAL_AUTH_SECRET` for local auth signing
- `POSTGRES_CORE_DB`, `POSTGRES_VECTOR_DB`, `POSTGRES_CORE_USER`, `POSTGRES_VECTOR_USER`, `POSTGRES_CORE_PASSWORD`, and `POSTGRES_VECTOR_PASSWORD` when overriding database defaults
- `OLLAMA_HOST` and `OLLAMA_BASE_URL` when connecting to a host Ollama service
- `LOCAL_CORE_DATA_HOST_DIR`, `LOCAL_CORE_POSTGRES_HOST_DIR`, and `LOCAL_CORE_LOGS_HOST_DIR` when moving data and logs outside the repository tree
- `TZ` for container timezone

Do not commit `.env`, local data, logs, backups, credentials, or generated runtime artifacts.

## Common Commands

```bash
docker compose ps
docker compose logs -f
docker compose logs -f backend
docker compose up -d --build
docker compose stop
docker compose down
```

Use `docker compose down -v` only when you intentionally want to remove Compose-managed volumes. Host-mounted data under `./data` and configured host directories are separate and should be backed up before destructive maintenance.

## Data and Backups

Default host-mounted paths include:

- PostgreSQL data: `${LOCAL_CORE_POSTGRES_HOST_DIR:-./data/postgres}`
- application data: `${LOCAL_CORE_DATA_HOST_DIR:-./data}`
- logs: `${LOCAL_CORE_LOGS_HOST_DIR:-./logs}`
- local secrets mount: `${LOCAL_CORE_SECRETS_HOST_DIR:-./data/secrets}`
- model cache: `${MINDSCAPE_MODELS_HOST_DIR:-${HOME}/.mindscape/models}`
- storage cache: `${MINDSCAPE_STORAGE_HOST_DIR:-${HOME}/.mindscape/storage}`

Use the backup helper before deleting containers, data directories, or database mounts:

```bash
scripts/backup_local_runtime.sh
scripts/verify_local_runtime_backup.sh <backup-dir>
```

The backup script creates PostgreSQL dumps, selected data archives, metadata, a manifest, and checksums. The verification script checks manifest artifacts, PostgreSQL dumps, and archive readability.

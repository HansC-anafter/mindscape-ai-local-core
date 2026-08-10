# Docker Deployment Guide

Docker Compose is the supported startup path for Mindscape AI Local Core.

## Prerequisites

- Docker with Docker Compose v2
- Git
- At least 8 GB of memory available to Docker for the default service set
- Enough disk space for container images, PostgreSQL data, model caches, and generated local data

LLM provider keys are optional for startup. The system can start with those keys unset, and AI features that need external LLM providers become available after configuration.

## Start

Clone the repository and start the default Docker services:

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
./scripts/start.sh
```

Linux and macOS users can also use the startup helper:

```bash
./scripts/start.sh
```

Windows PowerShell users can use:

```powershell
.\scripts\start.ps1
```

The helper scripts check Docker availability, bootstrap machine-owned runtime secrets, and can start host-side companion processes. On Unix-like hosts, `scripts/compose.sh` is the container-only compatibility facade; on Windows use `scripts\compose.ps1`.

## Update an Existing Installation

Run the installer in update mode from the existing repository directory. It keeps update, setup, secret bootstrap, and startup in one repository-owned flow:

macOS and Linux:

```bash
./install.sh --update
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Update
```

The installers use a fast-forward-only pull and stop on Git failure before running the existing setup and startup helpers. Those helpers own host preparation, machine-owned runtime-secret loading, and Compose startup. For a later container-only operation, use `./scripts/compose.sh <arguments>` on macOS/Linux or `.\scripts\compose.ps1 <arguments>` on Windows. Bare `docker compose` bypasses that runtime-secret boundary and is not a supported update or restart path.

## Startup Modes

The Compose facade starts the default container set while preserving the same runtime-secret bootstrap:

```bash
./scripts/compose.sh up -d
```

The macOS and Linux helper checks Docker, prepares repository-defined host companions when available, and then starts Compose with the `control-plane` profile:

```bash
./scripts/start.sh
```

The Windows helper checks Docker, prepares Windows host companions when available, and then starts the default Compose stack:

```powershell
.\scripts\start.ps1
```

Start the full official stack (all optional profiles) in one command:

```powershell
.\scripts\start.ps1 -FullStartup
```

Use the Compose facade for a container-only smoke test. Use the startup helper when you need the local host companions that are part of this repository's startup flow. Bare `docker compose` does not decrypt the Windows DPAPI store and is not a supported product startup path.

## Access

Default local access URLs:

- Web console: `http://localhost:8300`
- Backend service: `http://localhost:8200`
- OpenAPI docs: `http://localhost:8200/docs`
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
- `spillover`: starts `runner-spillover`
- `ha`: starts `postgres-replica`
- `legacy-xtts`: starts `xtts-service`
- `postgres-recovery-drill`: starts `postgres-recovery-drill-*`
- `runtime-db-observer`: starts `postgres-signal-observer`

Examples:

```bash
./scripts/compose.sh --profile control-plane up -d
./scripts/compose.sh --profile ocr up -d
```

To start the same full set as `.\scripts\start.ps1 -FullStartup` from Linux/macOS container-only path:

```bash
./scripts/compose.sh --profile control-plane --profile spillover --profile ha --profile ocr --profile legacy-xtts --profile postgres-recovery-drill --profile runtime-db-observer up -d
```

## Configuration

The repository includes `.env.example`. Copy it to `.env` when you need persistent local configuration:

```bash
cp .env.example .env
```

Useful settings include:

- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` for external LLM providers
- `LOCAL_AUTH_SECRET` for local auth signing
- `POSTGRES_CORE_DB`, `POSTGRES_VECTOR_DB`, and host directory settings when overriding public database defaults. The vector runtime password is machine-managed and must not be added to `.env`.
- `OLLAMA_HOST` and `OLLAMA_BASE_URL` when connecting to a host Ollama service
- `LOCAL_CORE_DATA_HOST_DIR`, `LOCAL_CORE_POSTGRES_HOST_DIR`, and `LOCAL_CORE_LOGS_HOST_DIR` when moving data and logs outside the repository tree
- `TZ` for container timezone
- `MOBILE_WORKBENCH_GATEWAY_ENABLED=1` to enable frontend allowlist mode for external gateway entry
- `MOBILE_WORKBENCH_GATEWAY_EXTRA_PATH_RULES` for additional allowed paths (comma separated), e.g. `"/api/v1/admin/preview,regex:^/custom-gateway/.+"`
- `MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS`, `MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_GROUPS` for identity allowlist
- `MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST` for operator workspace brakes; pack capability ingress is managed per workspace from the Gateway policy workbench
- `MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE`, `MOBILE_WORKBENCH_GATEWAY_JWT_ISSUER` for gateway JWT claim constraints
- `MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY` or `MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_FILE` and `MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION=1` for optional signature verification
- `MOBILE_WORKBENCH_GATEWAY_HEALTH_URL` if you need to override the settings-panel health surface target

Keep `.env`, local data, logs, backups, credentials, and generated runtime artifacts out of commits.

## Common Commands

```bash
./scripts/compose.sh ps
./scripts/compose.sh logs -f
./scripts/compose.sh logs -f backend
./scripts/compose.sh up -d --build
./scripts/compose.sh stop
./scripts/compose.sh down
```

Use `.\scripts\compose.ps1` with the same arguments on Windows PowerShell.

Use `./scripts/compose.sh down -v` (or `scripts\compose.ps1 down -v` on Windows) only when you intentionally want to remove Compose-managed volumes. Host-mounted data under `./data` and configured host directories are separate and should be backed up before destructive maintenance.

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

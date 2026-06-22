# Troubleshooting Guide

This guide covers common local startup issues for Mindscape AI Local Core.

## Docker Is Not Running

Check Docker:

```bash
docker info
docker compose version
```

If Docker is unavailable, start Docker Desktop on Windows or macOS. On Linux, start the Docker service according to your distribution.

## Port Already In Use

Default host ports include:

- `8200` for backend
- `8300` for frontend
- `5433` for PostgreSQL
- `6379` for Redis
- `8202` for media proxy
- `8020` for XTTS
- `8006` for Whisper
- `8001` for OCR when the `ocr` profile is enabled
- `8220` for the control-plane backend when the `control-plane` profile is enabled

Find the process using a port, stop it, or change the relevant host port mapping in a local Compose override.

Windows:

```powershell
netstat -ano | findstr :8200
```

macOS or Linux:

```bash
lsof -i :8200
```

## Existing Container Name Conflict

The Compose file uses stable container names. A previous stopped container can block startup.

Check:

```bash
docker ps -a --filter "name=mindscape-ai-local-core"
```

Remove the old project containers after confirming they are no longer needed:

```bash
docker compose down
```

If a stale container remains:

```bash
docker rm -f <container-name>
```

Back up local data before destructive maintenance.

## Backend Is Unhealthy

Check service status and logs:

```bash
docker compose ps
docker compose logs --tail=100 backend
```

The backend healthcheck uses:

```text
http://localhost:8200/healthz
```

Common causes include PostgreSQL not being healthy yet, Redis not being healthy yet, port conflicts, missing required environment overrides, or the backend still starting.

## Frontend Cannot Reach Backend

In the Docker stack, the frontend uses the backend service internally and exposes the browser-facing backend URL as `http://localhost:8200`.

Check:

```bash
docker compose logs --tail=100 frontend
curl http://localhost:8200/healthz
```

If running the frontend manually, ensure its environment points to the correct backend URL.

## Startup Helper Differs From Direct Compose

Direct Compose starts the container-only stack:

```bash
docker compose up -d
```

The macOS and Linux helper performs host-side setup first and then starts Compose with the `control-plane` profile:

```bash
./scripts/start.sh
```

The Windows helper performs Windows host-side setup first and then starts the default Compose stack:

```powershell
.\scripts\start.ps1
```

If a problem only appears when using a helper, check the helper output and host-side logs under `logs/` before changing Compose settings.

## PostgreSQL Problems

The default host PostgreSQL port is `5433`, mapped to container port `5432`.

Check:

```bash
docker compose ps postgres
docker compose logs --tail=100 postgres
```

The default data mount is:

```text
${LOCAL_CORE_POSTGRES_HOST_DIR:-./data/postgres}
```

Delete this directory only after creating and verifying a backup.

## Provider Keys Missing

The stack can start with `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` unset. Features that need those providers become available after keys are configured.

Create `.env` from the example when needed:

```bash
cp .env.example .env
```

Then restart services:

```bash
docker compose up -d
```

## Windows System Directory Error

If Docker tries to create project data under a protected system path, move the repository to a user-owned directory and run the startup command again.

Recommended locations:

```text
C:\Users\<you>\Documents\mindscape-ai-local-core
C:\Projects\mindscape-ai-local-core
D:\Projects\mindscape-ai-local-core
```

## PowerShell Script Policy

If PowerShell refuses to run the startup helper, set a user-level policy:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Or use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

## Backup Before Destructive Fixes

Before deleting containers, volumes, data directories, PostgreSQL mounts, or backup directories, create and verify a backup:

```bash
scripts/backup_local_runtime.sh
scripts/verify_local_runtime_backup.sh <backup-dir>
```

Keep backups outside any directory you plan to delete.

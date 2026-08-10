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
./scripts/compose.sh down
```

If a stale container remains:

```bash
docker rm -f <container-name>
```

Back up local data before destructive maintenance.

## Backend Is Unhealthy

Check service status and logs:

```bash
./scripts/compose.sh ps
./scripts/compose.sh logs --tail=100 backend
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
./scripts/compose.sh logs --tail=100 frontend
curl http://localhost:8200/healthz
```

If running the frontend manually, ensure its environment points to the correct backend URL.

## Startup Helper Differs From Direct Compose

The Compose facade starts the container-only stack after loading the machine-owned runtime secret:

```bash
./scripts/compose.sh up -d
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
./scripts/compose.sh ps postgres
./scripts/compose.sh logs --tail=100 postgres
```

The default data mount is:

```text
${LOCAL_CORE_POSTGRES_HOST_DIR:-./data/postgres}
```

Delete this directory only after creating and verifying a backup.

### HA replica startup on upgraded installs

On older installations that already have existing PostgreSQL data, enabling `ha` can fail with:

```text
FATAL: no pg_hba.conf entry for replication connection
```

This was fixed to self-heal on startup by this repository (`docker/postgres/bootstrap-postgres-entrypoint.sh`), which ensures replication `pg_hba.conf` entries exist before PostgreSQL starts.

If you still see the error after pulling the latest update, restart the primary PostgreSQL container so the reconciliation runs again:

```bash
./scripts/compose.sh up -d --force-recreate postgres
./scripts/compose.sh --profile ha up -d --force-recreate postgres-replica
./scripts/compose.sh logs --tail=120 postgres-replica
```

On Windows PowerShell:

```powershell
.\scripts\compose.ps1 up -d --force-recreate postgres
.\scripts\compose.ps1 --profile ha up -d --force-recreate postgres-replica
.\scripts\compose.ps1 logs --tail 120 postgres-replica
```

If this still persists, inspect `pg_hba.conf` for both `0.0.0.0/0` and `::/0` replication entries for `POSTGRES_USER` and restart `postgres-replica` after repair.

## FullStartup starts `restore_base_pg_version_missing`

If startup fails with `restore_base_pg_version_missing` after running `.\scripts\start.ps1 -FullStartup`, an operator-only disposable restore service was unintentionally included.

`postgres-disposable-restore` is intentionally isolated from the regular startup profile and must be launched only through:

`scripts/maintenance/postgres_disposable_restore.py`

Do not add placeholder `PG_VERSION` directories or disable restore preflights to work around this.
Update to a build containing the isolated `postgres-disposable-restore` profile, remove stale restore containers if present, and run FullStartup again.

## Full startup failure quick map

Use this when `scripts/start.ps1` exits with failed services.

| Symptom | Likely cause | What to run |
| --- | --- | --- |
| `restore_base_pg_version_missing` or `restore_base_pg_missing` | `postgres-disposable-restore` was started via `FullStartup` without a valid backup | Upgrade to the latest local-core build, then remove stale disposable restore containers and rerun `.\scripts\start.ps1 -FullStartup`. |
| `FATAL: no pg_hba.conf entry for replication connection ...` | Upgraded existing PostgreSQL volume lacks replication HBA entries | See the HA replica startup section above. |
| OCR service does not become healthy on startup | OCR image is stale or readiness probe is blocked | Run `.\scripts\compose.ps1 build --profile ocr ocr-service`, then rerun `.\scripts\start.ps1 -FullStartup`, then check `.\scripts\compose.ps1 logs ocr-service`. |
| `postgres is restarting` for one of the core services after first start | Service did not become healthy before the first readiness window | Run `.\scripts\compose.ps1 logs --tail=200 <service>` and `.\scripts\compose.ps1 ps` to capture logs and state. |

Example cleanup for stale restore containers (Windows):

```powershell
.\scripts\compose.ps1 stop postgres-recovery-restore postgres-recovery-restore-app-probe
.\scripts\compose.ps1 rm -f postgres-recovery-restore postgres-recovery-restore-app-probe
.\scripts\start.ps1 -FullStartup
```

On Unix shells:

```bash
./scripts/compose.sh stop postgres-recovery-restore postgres-recovery-restore-app-probe
./scripts/compose.sh rm -f postgres-recovery-restore postgres-recovery-restore-app-probe
./scripts/start.sh -FullStartup
```

(For Unix, replace `scripts/start.sh` with the correct startup entrypoint used in your environment.)
## Provider Keys Missing

The stack can start with `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` unset. Features that need those providers become available after keys are configured.

Create `.env` from the example when needed:

```bash
cp .env.example .env
```

Then restart services:

```bash
./scripts/compose.sh up -d
```

On Windows PowerShell, replace `./scripts/compose.sh` with `.\scripts\compose.ps1`. Do not repair internal database credential errors by adding `POSTGRES_VECTOR_RUNTIME_PASSWORD` to `.env`; rerun the canonical startup or Compose facade so the DPAPI-backed secret is loaded.

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

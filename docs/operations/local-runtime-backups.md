# Local Runtime Backups

This repo stores Docker runtime state in host-mounted directories. The backup
entrypoint is:

```bash
scripts/backup_local_runtime.sh
```

It writes backups under:

```text
${LOCAL_CORE_BACKUP_ROOT:-<LOCAL_CORE_DATA_HOST_DIR>/backups/local-runtime}
```

Each backup is first written to a `.partial` staging directory and is renamed
only after all requested artifacts pass local verification.

## Default Scope

The default backup includes:

- `mindscape_core` PostgreSQL custom dump
- `mindscape_vectors` PostgreSQL custom dump
- PostgreSQL globals dump
- `/app/data` archive
- runtime metadata
- IG browser profile `storage_state.json` validation report
- `manifest.json`
- `SHA256SUMS`

The `/app/data` archive excludes these by default:

- `/app/data/postgres`
- `/app/data/backups`
- `/app/data/ig_thumbnails`
- `/app/data/e2e-traces`

The exclusions avoid recursive backups and large generated/cache directories.
Use `--full` when the thumbnail cache and traces must be preserved too.

## Commands

Create the standard backup:

```bash
scripts/backup_local_runtime.sh
```

Create a full backup, including IG thumbnails and e2e traces:

```bash
scripts/backup_local_runtime.sh --full
```

Include logs:

```bash
scripts/backup_local_runtime.sh --include-logs
```

Print the resolved backup plan without writing files:

```bash
scripts/backup_local_runtime.sh --dry-run
```

Verify a backup:

```bash
scripts/verify_local_runtime_backup.sh /path/to/backup-dir
```

## Verification Guarantees

The backup script refuses to complete if:

- a PostgreSQL dump is empty
- `pg_restore --list` cannot read a custom dump
- an archive is empty
- `tar -tzf` cannot read an archive
- a backup with the same final name already exists
- another backup lock is active

The verify script checks:

- `manifest.json` can be parsed
- every manifest artifact exists and is non-empty
- artifact sizes match the manifest
- artifact SHA-256 checksums match
- PostgreSQL custom dumps can be listed
- archives can be listed

## Current Redis Boundary

Redis is not part of durable backup scope by default. The current compose
configuration runs Redis with:

```text
--save ""
--appendonly no
```

That means Redis is treated as transient runtime state. Durable queues or
state that must survive host loss should be stored in PostgreSQL or files under
the host-mounted data root.

## Restore Notes

For PostgreSQL, use a clean target database and restore with `pg_restore`.
For file data, unpack `archives/app-data.tar.gz` into the same mount layout.
Do not restore over a running production-like local runtime without first
stopping services and taking a fresh backup.

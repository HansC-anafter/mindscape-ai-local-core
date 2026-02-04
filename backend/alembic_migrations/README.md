# Alembic Database Migrations

This directory contains database migration scripts managed by Alembic.

## Overview

Alembic is used to manage database schema changes in a version-controlled, reversible manner. All schema modifications should be done through Alembic migrations rather than direct SQL DDL.

## Database Configuration

The migrations are configured for the main SQLite database:
- **Database**: `data/my_agent_console.db`
- **Configuration**: `alembic.ini` (in parent directory)

## Common Commands

### Create a new migration

```bash
cd backend
alembic revision -m "description of changes"
```

### Auto-generate migration (requires SQLAlchemy models)

```bash
alembic revision --autogenerate -m "description of changes"
```

### Apply migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade one version
alembic upgrade +1

# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision>
```

### View migration status

```bash
# Show current version
alembic current

# Show migration history
alembic history

# Show pending migrations
alembic heads
```

## Migration Files

Migration files are located in `versions/` directory and follow the naming pattern:
- `{revision}_{description}.py`

Each migration file contains:
- `revision`: Unique identifier
- `down_revision`: Previous migration revision
- `upgrade()`: Function to apply changes
- `downgrade()`: Function to revert changes

## Current Baseline

The initial migration (`001_initial_schema.py`) serves as a baseline reference point for all existing tables. Since tables were created via direct SQL DDL, this migration is a no-op but documents the current schema state.

## Best Practices

1. **Always test migrations** in a development environment first
2. **Backup database** before applying migrations in production
3. **Write reversible migrations** - ensure downgrade() properly reverses upgrade()
4. **Use descriptive messages** when creating migrations
5. **Review auto-generated migrations** before committing
6. **One logical change per migration** - keep migrations focused

## Notes

- Current implementation uses direct SQL (not SQLAlchemy ORM)
- Future migrations should modify schema through Alembic
- Existing `CREATE TABLE IF NOT EXISTS` logic can remain as fallback
- Multiple databases (e.g., `tool_registry.db`) may require separate Alembic configurations


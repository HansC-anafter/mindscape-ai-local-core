# PostgreSQL Migration Verification Framework

This directory contains the persistent automated testing suite for the `local-core` PostgreSQL migration.
This framework is used to verify the correctness of the system under the PostgreSQL architecture and serves as a baseline for long-term regression testing.

## Structure

Tests are categorized by "Architectural Layers" and "Capabilities" rather than temporary migration phases.

```text
backend/tests/migration/postgres/
├── conftest.py                # Shared global fixtures (DB connection, data context)
├── fixtures/                  # Static test data (SQL dumps, JSONs)
├── infrastructure/            # [Infrastructure Layer] Adapter & Connection verification
│   ├── test_connection.py     # Connection Factory & Config tests
│   └── test_adapters.py       # StoreBase & Adapter tests
├── capabilities/              # [Capability Layer] Business logic verification
│   ├── test_pack_ig.py        # IG Pack independent verification
│   ├── test_core_identity.py  # Identity (Profile/Workspace) verification
│   ├── test_core_ops.py       # Operations (Events/Intents) verification
│   └── test_lens.py           # Lens & Artifacts verification
└── integrity/                 # [System Integrity] System constraints & normative verification
    └── test_db_usage.py       # Assert no SQLite usage, Schema integrity
```

## Usage

Please use the unified entry script located in the root directory to run tests:

```bash
# Verify everything
python scripts/verify_postgres_migration.py --scope=all

# Verify Infrastructure Layer only
python scripts/verify_postgres_migration.py --scope=infra

# Verify specific Capability Group
python scripts/verify_postgres_migration.py --scope=caps --group=ig
```

## Maintenance Guide

1. **Long-term Maintenance**: This is not a one-off script. All changes to the DB layer must pass these tests.
2. **New Capabilities**: When adding a new Pack or feature, add corresponding tests under `capabilities/`.
3. **Architectural Changes**: If modifying `StoreBase` or connection logic, verify and extend `infrastructure/` tests first.

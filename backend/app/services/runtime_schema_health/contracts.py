"""Runtime schema readiness contract constants."""

ACCESS_TABLES = (
    "access_principals",
    "access_identity_bindings",
    "access_grants",
)
RUNTIME_UPGRADE_COMMAND = (
    "python backend/app/services/migrations/cli.py apply --db postgres"
)

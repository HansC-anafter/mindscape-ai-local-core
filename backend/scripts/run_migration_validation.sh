#!/bin/bash
# Tool Registry Migration and Validation Script
#
# This script runs the migration and validation scripts for Runtime Profile support.
# It generates a comprehensive migration report.
#
# Usage:
#   ./run_migration_validation.sh [--db-path PATH] [--dry-run]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="$PROJECT_ROOT/docs-internal/implementation/migration-reports"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="$REPORT_DIR/tool_registry_migration_report_${TIMESTAMP}.md"

# Default database path
DB_PATH="${DB_PATH:-./data/tool_registry.db}"

# Parse arguments
DRY_RUN=false
if [[ "$*" == *"--dry-run"* ]]; then
    DRY_RUN=true
fi

if [[ "$*" == *"--db-path"* ]]; then
    # Extract db-path value
    for arg in "$@"; do
        if [[ $arg == --db-path=* ]]; then
            DB_PATH="${arg#*=}"
        elif [[ $arg == --db-path ]]; then
            # Next argument is the path
            continue
        fi
    done
fi

# Create report directory
mkdir -p "$REPORT_DIR"

echo "=========================================="
echo "Tool Registry Migration & Validation"
echo "=========================================="
echo "Database: $DB_PATH"
echo "Dry Run: $DRY_RUN"
echo "Report: $REPORT_FILE"
echo ""

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "⚠️  Warning: Database not found at $DB_PATH"
    echo "   This may be expected if using a different database backend."
    echo "   Skipping migration (database may not use SQLite)."
    echo ""

    # Generate report for non-SQLite case
    cat > "$REPORT_FILE" <<EOF
# Tool Registry Migration Report

**Date:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Database Path:** $DB_PATH
**Status:** ⚠️ Database not found (may use different backend)

## Summary

The migration script was not executed because the database file was not found at the specified path.
This may be expected if:
- The system uses a different database backend (PostgreSQL, MySQL, etc.)
- The database is managed by a different service
- The database file is located elsewhere

## Recommendations

1. **Check database backend**: Verify which database backend is being used
2. **Locate database**: Find the actual database location
3. **Manual migration**: If using a different backend, perform manual migration:
   - Add `capability_code` column (TEXT, default '')
   - Add `risk_class` column (TEXT, default 'readonly')
   - Run migration logic to populate these fields

## Migration Logic

The migration script performs the following:
1. Adds `capability_code` column (defaults to `origin_capability_id` if available)
2. Adds `risk_class` column (maps from `side_effect_level` or `danger_level`)
3. Updates all existing tools with appropriate values

## Validation Requirements

After migration, all tools should have:
- `capability_code`: Non-empty string (or can use `origin_capability_id` as fallback)
- `risk_class`: One of: "readonly", "soft_write", "external_write", "destructive"

EOF
    echo "Report generated: $REPORT_FILE"
    exit 0
fi

# Step 1: Pre-migration validation
echo "Step 1: Pre-migration validation..."
echo "-----------------------------------"
python3 -m backend.scripts.validate_tool_registry_runtime_profile --db-path "$DB_PATH" > "$REPORT_DIR/pre_migration_validation_${TIMESTAMP}.txt" 2>&1 || true
PRE_VALIDATION_EXIT_CODE=$?

if [ $PRE_VALIDATION_EXIT_CODE -eq 0 ]; then
    echo "✓ Pre-migration validation passed (all tools already have required fields)"
    PRE_MIGRATION_STATUS="✅ Already migrated"
else
    echo "⚠️  Pre-migration validation found issues (expected before migration)"
    PRE_MIGRATION_STATUS="⚠️ Needs migration"
fi
echo ""

# Step 2: Migration (dry-run first if requested)
if [ "$DRY_RUN" = true ]; then
    echo "Step 2: Migration (DRY RUN)..."
    echo "-----------------------------------"
    python3 -m backend.scripts.migrate_tool_registry_for_runtime_profile --db-path "$DB_PATH" --dry-run > "$REPORT_DIR/migration_dry_run_${TIMESTAMP}.txt" 2>&1
    MIGRATION_STATUS="🔍 Dry run completed (no changes applied)"
else
    echo "Step 2: Migration..."
    echo "-----------------------------------"
    python3 -m backend.scripts.migrate_tool_registry_for_runtime_profile --db-path "$DB_PATH" > "$REPORT_DIR/migration_${TIMESTAMP}.txt" 2>&1
    MIGRATION_EXIT_CODE=$?

    if [ $MIGRATION_EXIT_CODE -eq 0 ]; then
        echo "✓ Migration completed successfully"
        MIGRATION_STATUS="✅ Completed"
    else
        echo "✗ Migration failed (exit code: $MIGRATION_EXIT_CODE)"
        MIGRATION_STATUS="❌ Failed"
    fi
fi
echo ""

# Step 3: Post-migration validation
if [ "$DRY_RUN" = false ]; then
    echo "Step 3: Post-migration validation..."
    echo "-----------------------------------"
    python3 -m backend.scripts.validate_tool_registry_runtime_profile --db-path "$DB_PATH" > "$REPORT_DIR/post_migration_validation_${TIMESTAMP}.txt" 2>&1
    POST_VALIDATION_EXIT_CODE=$?

    if [ $POST_VALIDATION_EXIT_CODE -eq 0 ]; then
        echo "✓ Post-migration validation passed"
        POST_MIGRATION_STATUS="✅ All tools valid"
    else
        echo "⚠️  Post-migration validation found issues"
        POST_MIGRATION_STATUS="⚠️ Some tools need attention"
    fi
    echo ""
fi

# Generate comprehensive report
cat > "$REPORT_FILE" <<EOF
# Tool Registry Migration Report

**Date:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Database Path:** $DB_PATH
**Dry Run:** $DRY_RUN

## Executive Summary

| Step | Status |
|------|--------|
| Pre-migration Validation | $PRE_MIGRATION_STATUS |
| Migration | $MIGRATION_STATUS |
EOF

if [ "$DRY_RUN" = false ]; then
    cat >> "$REPORT_FILE" <<EOF
| Post-migration Validation | $POST_MIGRATION_STATUS |
EOF
fi

cat >> "$REPORT_FILE" <<EOF

## Detailed Results

### Pre-migration Validation

\`\`\`
$(cat "$REPORT_DIR/pre_migration_validation_${TIMESTAMP}.txt")
\`\`\`

### Migration

\`\`\`
$(cat "$REPORT_DIR/migration_${TIMESTAMP}.txt" 2>/dev/null || cat "$REPORT_DIR/migration_dry_run_${TIMESTAMP}.txt" 2>/dev/null || echo "Migration output not available")
\`\`\`

EOF

if [ "$DRY_RUN" = false ]; then
    cat >> "$REPORT_FILE" <<EOF
### Post-migration Validation

\`\`\`
$(cat "$REPORT_DIR/post_migration_validation_${TIMESTAMP}.txt")
\`\`\`

EOF
fi

cat >> "$REPORT_FILE" <<EOF
## Migration Details

### What Was Migrated

1. **Added Columns:**
   - \`capability_code\` (TEXT, default ''): Capability code for policy matching
   - \`risk_class\` (TEXT, default 'readonly'): Risk class for confirmation policy

2. **Data Mapping:**
   - \`capability_code\`: Defaults to \`origin_capability_id\` if available
   - \`risk_class\`: Mapped from \`side_effect_level\` or \`danger_level\`
     - \`side_effect_level\` → \`risk_class\`:
       - "readonly" → "readonly"
       - "soft_write" → "soft_write"
       - "external_write" → "external_write"
     - \`danger_level\` → \`risk_class\` (fallback):
       - "high" → "external_write"
       - "medium" → "soft_write"
       - "low" → "readonly"

### Validation Requirements

After migration, all tools should have:
- ✅ \`capability_code\`: Non-empty string (or can use \`origin_capability_id\` as fallback)
- ✅ \`risk_class\`: One of: "readonly", "soft_write", "external_write", "destructive"

## Next Steps

1. **Review Results**: Check the validation output for any tools that need attention
2. **Manual Fixes**: If any tools are missing required fields, update them manually:
   - Set \`capability_code\` based on tool purpose
   - Set \`risk_class\` based on tool's side effects
3. **Re-run Validation**: Run validation script again to confirm all tools are valid
4. **Test Runtime Profile**: Verify PolicyGuard works correctly with migrated tools

## Files Generated

- Pre-migration validation: \`pre_migration_validation_${TIMESTAMP}.txt\`
- Migration output: \`migration_${TIMESTAMP}.txt\` (or \`migration_dry_run_${TIMESTAMP}.txt\`)
EOF

if [ "$DRY_RUN" = false ]; then
    cat >> "$REPORT_FILE" <<EOF
- Post-migration validation: \`post_migration_validation_${TIMESTAMP}.txt\`
EOF
fi

cat >> "$REPORT_FILE" <<EOF
- Migration report: \`tool_registry_migration_report_${TIMESTAMP}.md\`

## Related Documentation

- [Runtime Profile Architecture Assessment](../workspace-runtime-profile-architecture-assessment-2025-12-28.md)
- [Runtime Profile Gap Analysis](../workspace-runtime-profile-gap-analysis-2025-12-29.md)
- [Runtime Profile Implementation Completion](../workspace-runtime-profile-implementation-completion-2025-12-29.md)

---

**Generated by:** \`run_migration_validation.sh\`
**Script version:** 1.0
EOF

echo "=========================================="
echo "Migration Report Generated"
echo "=========================================="
echo "Report: $REPORT_FILE"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "⚠️  This was a dry run. To apply changes, run:"
    echo "   ./run_migration_validation.sh --db-path $DB_PATH"
else
    if [ $POST_VALIDATION_EXIT_CODE -eq 0 ]; then
        echo "✅ Migration completed successfully!"
        echo "   All tools have required fields."
    else
        echo "⚠️  Migration completed, but some tools need attention."
        echo "   Check the report for details."
    fi
fi






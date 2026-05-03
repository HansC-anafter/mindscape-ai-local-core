"""
DEPRECATED: This script is for legacy SQLite tool_registry.db migration.
PostgreSQL is now the primary database. This script is retained for historical reference only.
Last updated: 2026-01-27

Generate Tool Registry Migration Report

This script generates a comprehensive migration report for Runtime Profile support.
It can work in two modes:
1. If database exists and dependencies are available: Execute actual migration/validation
2. Otherwise: Generate a template report with instructions

Usage:
    python -m backend.scripts.generate_migration_report [--db-path PATH] [--dry-run]
"""

import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def check_database_exists(db_path: str) -> bool:
    """Check if database file exists"""
    return Path(db_path).exists()


def check_dependencies() -> bool:
    """Check if required dependencies are available"""
    try:
        import sqlite3

        return True
    except ImportError:
        return False


def execute_validation(db_path: str) -> Dict[str, Any]:
    """Execute validation script and return results"""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.scripts.validate_tool_registry_runtime_profile",
                "--db-path",
                db_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_migration(db_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """Execute migration script and return results"""
    try:
        cmd = [
            sys.executable,
            "-m",
            "backend.scripts.migrate_tool_registry_for_runtime_profile",
            "--db-path",
            db_path,
        ]
        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "dry_run": dry_run,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "dry_run": dry_run}


def generate_template_report(db_path: str, dry_run: bool = False) -> str:
    """Generate template report with instructions"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    report = f"""# Tool Registry Migration Report

**Date:** {timestamp}
**Database Path:** {db_path}
**Dry Run:** {dry_run}
**Status:** ⚠️ Template Report (Migration not executed)

## Executive Summary

| Step | Status |
|------|--------|
| Database Check | {'✅ Found' if check_database_exists(db_path) else '❌ Not Found'} |
| Dependencies Check | {'✅ Available' if check_dependencies() else '❌ Missing'} |
| Pre-migration Validation | ⏳ Not Executed |
| Migration | ⏳ Not Executed |
| Post-migration Validation | ⏳ Not Executed |

## Migration Instructions

### Prerequisites

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Verify Database Location:**
   - Default: `./data/tool_registry.db`
   - Or specify with: `--db-path /path/to/tool_registry.db`

3. **Backup Database (Recommended):**
   ```bash
   cp data/tool_registry.db data/tool_registry.db.backup
   ```

### Execution Steps

#### Step 1: Pre-migration Validation

```bash
python -m backend.scripts.validate_tool_registry_runtime_profile --db-path {db_path}
```

**Expected Output:**
- If columns missing: Warning about missing columns
- If tools missing fields: List of tools that need migration

#### Step 2: Migration (Dry Run)

```bash
python -m backend.scripts.migrate_tool_registry_for_runtime_profile --db-path {db_path} --dry-run
```

**Expected Output:**
- List of tools that will be updated
- Summary of changes (no actual changes applied)

#### Step 3: Migration (Actual)

```bash
python -m backend.scripts.migrate_tool_registry_for_runtime_profile --db-path {db_path}
```

**Expected Output:**
- List of tools updated
- Migration summary with statistics

#### Step 4: Post-migration Validation

```bash
python -m backend.scripts.validate_tool_registry_runtime_profile --db-path {db_path}
```

**Expected Output:**
- ✅ All tools are valid! (if successful)
- Or list of tools that still need attention

### Alternative: Use Shell Script

```bash
./backend/scripts/run_migration_validation.sh --db-path {db_path}
```

Or with dry-run:
```bash
./backend/scripts/run_migration_validation.sh --db-path {db_path} --dry-run
```

## Migration Details

### What Will Be Migrated

1. **Added Columns:**
   - `capability_code` (TEXT, default ''): Capability code for policy matching
   - `risk_class` (TEXT, default 'readonly'): Risk class for confirmation policy

2. **Data Mapping:**
   - `capability_code`: Defaults to `origin_capability_id` if available
   - `risk_class`: Mapped from `side_effect_level` or `danger_level`
     - `side_effect_level` → `risk_class`:
       - "readonly" → "readonly"
       - "soft_write" → "soft_write"
       - "external_write" → "external_write"
     - `danger_level` → `risk_class` (fallback):
       - "high" → "external_write"
       - "medium" → "soft_write"
       - "low" → "readonly"

### Validation Requirements

After migration, all tools should have:
- ✅ `capability_code`: Non-empty string (or can use `origin_capability_id` as fallback)
- ✅ `risk_class`: One of: "readonly", "soft_write", "external_write", "destructive"

## Troubleshooting

### Issue: ModuleNotFoundError

**Solution:**
```bash
# Install dependencies
pip install -r requirements.txt

# Or activate virtual environment
source venv/bin/activate  # or your venv path
```

### Issue: Database Not Found

**Solution:**
1. Check if database exists at specified path
2. If using different backend (PostgreSQL, MySQL), perform manual migration:
   - Add `capability_code` column
   - Add `risk_class` column
   - Run migration logic to populate fields

### Issue: Migration Fails

**Solution:**
1. Check database permissions
2. Verify database is not locked by another process
3. Check migration script logs for specific errors
4. Restore from backup if needed

## Next Steps

1. **Execute Migration**: Follow the instructions above to run migration
2. **Review Results**: Check validation output for any tools that need attention
3. **Manual Fixes**: If any tools are missing required fields, update them manually
4. **Re-run Validation**: Run validation script again to confirm all tools are valid
5. **Test Runtime Profile**: Verify PolicyGuard works correctly with migrated tools

## Related Documentation

- [Runtime Profile Architecture Assessment](../../docs-internal/implementation/workspace-runtime-profile-architecture-assessment-2025-12-28.md)
- [Runtime Profile Gap Analysis](../../docs-internal/implementation/workspace-runtime-profile-gap-analysis-2025-12-29.md)
- [Runtime Profile Implementation Completion](../../docs-internal/implementation/workspace-runtime-profile-implementation-completion-2025-12-29.md)

---

**Generated by:** `generate_migration_report.py`
**Script version:** 1.0
**Note:** This is a template report. Execute the migration scripts to generate actual results.
"""
    return report


def generate_actual_report(db_path: str, dry_run: bool = False) -> str:
    """Generate report from actual migration execution"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Pre-migration validation
    pre_validation = execute_validation(db_path)

    # Migration
    migration = execute_migration(db_path, dry_run=dry_run)

    # Post-migration validation (only if not dry-run)
    post_validation = None
    if not dry_run:
        post_validation = execute_validation(db_path)

    # Build report
    report = f"""# Tool Registry Migration Report

**Date:** {timestamp}
**Database Path:** {db_path}
**Dry Run:** {dry_run}

## Executive Summary

| Step | Status |
|------|--------|
| Pre-migration Validation | {'✅ Passed' if pre_validation.get('success') else '⚠️ Issues Found'} |
| Migration | {'✅ Completed' if migration.get('success') else '❌ Failed'} |
"""

    if post_validation:
        report += f"""| Post-migration Validation | {'✅ Passed' if post_validation.get('success') else '⚠️ Issues Found'} |
"""

    report += f"""
## Detailed Results

### Pre-migration Validation

```
{pre_validation.get('stdout', pre_validation.get('error', 'No output'))}
```

### Migration

```
{migration.get('stdout', migration.get('error', 'No output'))}
"""

    if post_validation:
        report += f"""
### Post-migration Validation

```
{post_validation.get('stdout', post_validation.get('error', 'No output'))}
```
"""

    report += """
## Migration Details

### What Was Migrated

1. **Added Columns:**
   - `capability_code` (TEXT, default ''): Capability code for policy matching
   - `risk_class` (TEXT, default 'readonly'): Risk class for confirmation policy

2. **Data Mapping:**
   - `capability_code`: Defaults to `origin_capability_id` if available
   - `risk_class`: Mapped from `side_effect_level` or `danger_level`

## Next Steps

1. **Review Results**: Check the validation output for any tools that need attention
2. **Manual Fixes**: If any tools are missing required fields, update them manually
3. **Re-run Validation**: Run validation script again to confirm all tools are valid
4. **Test Runtime Profile**: Verify PolicyGuard works correctly with migrated tools

---
"""

    return report


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Tool Registry Migration Report"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./data/tool_registry.db",
        help="Path to tool_registry database",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run mode (for migration)"
    )
    parser.add_argument(
        "--output", type=str, help="Output file path (default: auto-generated)"
    )
    parser.add_argument(
        "--force-template",
        action="store_true",
        help="Force template report (don't execute migration)",
    )

    args = parser.parse_args()

    # Generate report
    if (
        args.force_template
        or not check_database_exists(args.db_path)
        or not check_dependencies()
    ):
        report = generate_template_report(args.db_path, args.dry_run)
    else:
        report = generate_actual_report(args.db_path, args.dry_run)

    # Save report
    if args.output:
        output_path = Path(args.output)
    else:
        report_dir = (
            Path(__file__).parent.parent.parent
            / "docs-internal"
            / "implementation"
            / "migration-reports"
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = report_dir / f"tool_registry_migration_report_{timestamp}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Migration report generated: {output_path}")
    print()
    print("Report Summary:")
    print(f"  Database: {args.db_path}")
    print(f"  Exists: {'✅' if check_database_exists(args.db_path) else '❌'}")
    print(f"  Dependencies: {'✅' if check_dependencies() else '❌'}")
    print(
        f"  Report Type: {'Template' if args.force_template or not check_database_exists(args.db_path) or not check_dependencies() else 'Actual'}"
    )


if __name__ == "__main__":
    main()

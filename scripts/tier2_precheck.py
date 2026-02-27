#!/usr/bin/env python3
"""
Tier 2 Pre-Check: Category C/D Store Classification Guard

Scans backend/app/ for Store(...db_path...) patterns and classifies each hit
as Category C (safe to clean — already PostgresStoreBase) or Category D
(StoreBase — MUST NOT remove db_path until Postgres migration is done).

Exit codes:
  0  — all clear (only Category C residuals, or zero residuals)
  1  — Category D stores found with db_path removed (regression risk)

Usage:
    python scripts/tier2_precheck.py            # scan only
    python scripts/tier2_precheck.py --strict   # exit 1 if any Category D residual found

Design rationale:
  Category C stores inherit PostgresStoreBase; their __init__ accepts db_path
  but ignores it. Removing db_path is safe cosmetic cleanup.

  Category D stores inherit StoreBase; their __init__ REQUIRES db_path.
  Removing db_path causes TypeError at runtime.
"""

import re
import sys
import os
from pathlib import Path

# ── Store classification ──────────────────────────────────────────────
# Category C: already on PostgresStoreBase, db_path accepted but ignored
CATEGORY_C = {
    "TasksStore",
    "IntentTagsStore",
    "ConfigStore",
    "AIRoleStore",
    "IntentClustersStore",
    "ToolCallsStore",
    "StageResultsStore",
    "SystemSettingsStore",
}

# Category D: still on StoreBase, db_path REQUIRED
CATEGORY_D = {
    "TimelineItemsStore",
    "TaskPreferenceStore",
    "TaskFeedbackStore",
    "SavedViewsStore",
    "ProjectPhasesStore",
    "RunnerLocksStore",
    "BackgroundRoutinesStore",
    "IntentLogsStore",
    "EntitiesStore",
    "ArtifactRegistryStore",
}

# Category E: standalone, db_path may or may not be required
CATEGORY_E = {
    "ControlProfileStore",  # db_path REQUIRED (file-based)
    "WorkspaceRuntimeProfileStore",  # db_path Optional
}

# Stores where empty constructor () is a REGRESSION
REQUIRES_DB_PATH = CATEGORY_D | {"ControlProfileStore"}

# ── Pattern matchers ──────────────────────────────────────────────────
# Matches: SomethingStore() with NO arguments — potential regression
# Use negative lookbehind (?<!Postgres) to exclude PostgresXxxStore() which is correct
EMPTY_CTOR_RE = re.compile(r"(?<!Postgres)(" + "|".join(REQUIRES_DB_PATH) + r")\(\s*\)")

# Matches: SomethingStore(db_path) or SomethingStore(xxx.db_path)
DB_PATH_ARG_RE = re.compile(r"(" + "|".join(CATEGORY_C) + r")\([^)]*db_path")


def scan_file(filepath: Path):
    """Scan a single Python file for store constructor issues."""
    issues = []
    info = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return issues, info

    for lineno, line in enumerate(content.splitlines(), 1):
        # Skip comments and class definitions
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("class "):
            continue

        # Check for Category D stores with empty constructor (REGRESSION)
        for m in EMPTY_CTOR_RE.finditer(line):
            store_name = m.group(1)
            issues.append(
                {
                    "file": str(filepath),
                    "line": lineno,
                    "store": store_name,
                    "category": "D" if store_name in CATEGORY_D else "E",
                    "content": stripped,
                }
            )

        # Check for Category C stores still passing db_path (safe but noisy)
        for m in DB_PATH_ARG_RE.finditer(line):
            store_name = m.group(1)
            info.append(
                {
                    "file": str(filepath),
                    "line": lineno,
                    "store": store_name,
                    "category": "C",
                    "content": stripped,
                }
            )

    return issues, info


def main():
    strict = "--strict" in sys.argv

    # Resolve project root
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    app_dir = project_root / "backend" / "app"

    if not app_dir.exists():
        print(f"ERROR: {app_dir} not found. Run from project root.")
        sys.exit(2)

    all_issues = []
    all_info = []

    for py_file in app_dir.rglob("*.py"):
        # Skip deprecated and __pycache__
        rel = str(py_file.relative_to(app_dir))
        if "deprecated" in rel or "__pycache__" in rel:
            continue

        issues, info = scan_file(py_file)
        all_issues.extend(issues)
        all_info.extend(info)

    # ── Report ────────────────────────────────────────────────────────
    print("=" * 60)
    print("Tier 2 Pre-Check: Category C/D Store Classification")
    print("=" * 60)

    if all_issues:
        print(
            f"\n❌ REGRESSION RISK: {len(all_issues)} Category D/E store(s) "
            f"called without db_path:\n"
        )
        for issue in sorted(all_issues, key=lambda x: (x["file"], x["line"])):
            cat = issue["category"]
            print(f"  [{cat}] {issue['file']}:{issue['line']}")
            print(f"      {issue['store']}() — db_path REQUIRED")
            print(f"      > {issue['content']}")
            print()
    else:
        print("\n✅ No Category D/E regressions found.")

    if all_info:
        print(
            f"\nℹ️  {len(all_info)} Category C store(s) still pass db_path "
            f"(safe, but could be cleaned):\n"
        )
        for info in sorted(all_info, key=lambda x: (x["file"], x["line"]))[:10]:
            print(f"  [C] {info['file']}:{info['line']}")
            print(f"      > {info['content']}")
        if len(all_info) > 10:
            print(f"  ... and {len(all_info) - 10} more")
    else:
        print("\nℹ️  No Category C db_path residuals found (fully clean).")

    print("\n" + "=" * 60)

    if all_issues and strict:
        print("STRICT MODE: Exiting with code 1 due to regressions.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

"""
Tool Registry Validation Script for Runtime Profile

Validates that all RegisteredTool records have capability_code and risk_class fields.

Usage:
    python -m backend.scripts.validate_tool_registry_runtime_profile [--db-path PATH]
"""

import sqlite3
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.models.tool_registry import RegisteredTool


def get_db_path(db_path: Optional[str] = None) -> str:
    """Get database path"""
    if db_path:
        return db_path

    # Default: use data directory
    data_dir = Path("./data")
    return str(data_dir / "tool_registry.db")


def validate_tool_registry(db_path: str) -> Dict[str, Any]:
    """
    Validate tool registry for Runtime Profile requirements

    Args:
        db_path: Path to tool_registry database

    Returns:
        Validation results
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if columns exist
    cursor.execute("PRAGMA table_info(tool_registry)")
    columns = [row[1] for row in cursor.fetchall()]

    has_capability_code = "capability_code" in columns
    has_risk_class = "risk_class" in columns

    results = {
        "total_tools": 0,
        "valid_tools": 0,
        "invalid_tools": [],
        "missing_capability_code": [],
        "missing_risk_class": [],
        "invalid_risk_class": [],
        "columns_exist": {
            "capability_code": has_capability_code,
            "risk_class": has_risk_class,
        }
    }

    if not has_capability_code or not has_risk_class:
        print("⚠️  Warning: Required columns missing. Run migration script first.")
        print(f"   capability_code: {has_capability_code}")
        print(f"   risk_class: {has_risk_class}")
        conn.close()
        return results

    # Load all tools
    cursor.execute("SELECT * FROM tool_registry")
    rows = cursor.fetchall()
    results["total_tools"] = len(rows)

    # Valid risk classes
    valid_risk_classes = {"readonly", "soft_write", "external_write", "destructive"}

    # Validate each tool
    for row in rows:
        tool_id = row["tool_id"]
        capability_code = row.get("capability_code") or ""
        risk_class = row.get("risk_class") or ""
        origin_capability_id = row.get("origin_capability_id", "")

        is_valid = True
        issues = []

        # Check capability_code
        if not capability_code:
            if origin_capability_id:
                # Can use origin_capability_id as fallback, but should be set
                issues.append("capability_code empty (has origin_capability_id fallback)")
            else:
                issues.append("capability_code missing and no origin_capability_id")
                results["missing_capability_code"].append(tool_id)
                is_valid = False

        # Check risk_class
        if not risk_class:
            issues.append("risk_class missing")
            results["missing_risk_class"].append(tool_id)
            is_valid = False
        elif risk_class not in valid_risk_classes:
            issues.append(f"invalid risk_class: {risk_class}")
            results["invalid_risk_class"].append(tool_id)
            is_valid = False

        if is_valid:
            results["valid_tools"] += 1
        else:
            results["invalid_tools"].append({
                "tool_id": tool_id,
                "issues": issues
            })

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate tool registry for Runtime Profile support"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to tool_registry database (default: ./data/tool_registry.db)"
    )

    args = parser.parse_args()

    db_path = get_db_path(args.db_path)

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f"Validating tool registry: {db_path}")
    print()

    results = validate_tool_registry(db_path)

    # Print results
    print("Validation Results:")
    print(f"  Total tools: {results['total_tools']}")
    print(f"  Valid tools: {results['valid_tools']}")
    print(f"  Invalid tools: {len(results['invalid_tools'])}")
    print()

    if results['columns_exist']['capability_code'] and results['columns_exist']['risk_class']:
        print("✓ Required columns exist")
    else:
        print("✗ Required columns missing")
        if not results['columns_exist']['capability_code']:
            print("  - capability_code column missing")
        if not results['columns_exist']['risk_class']:
            print("  - risk_class column missing")
        print()
        print("Run migration script first:")
        print("  python -m backend.scripts.migrate_tool_registry_for_runtime_profile")
        sys.exit(1)

    if results['missing_capability_code']:
        print(f"⚠️  Tools missing capability_code: {len(results['missing_capability_code'])}")
        for tool_id in results['missing_capability_code'][:10]:
            print(f"     - {tool_id}")
        if len(results['missing_capability_code']) > 10:
            print(f"     ... and {len(results['missing_capability_code']) - 10} more")

    if results['missing_risk_class']:
        print(f"⚠️  Tools missing risk_class: {len(results['missing_risk_class'])}")
        for tool_id in results['missing_risk_class'][:10]:
            print(f"     - {tool_id}")
        if len(results['missing_risk_class']) > 10:
            print(f"     ... and {len(results['missing_risk_class']) - 10} more")

    if results['invalid_risk_class']:
        print(f"⚠️  Tools with invalid risk_class: {len(results['invalid_risk_class'])}")
        for tool_id in results['invalid_risk_class'][:10]:
            print(f"     - {tool_id}")
        if len(results['invalid_risk_class']) > 10:
            print(f"     ... and {len(results['invalid_risk_class']) - 10} more")

    if results['invalid_tools']:
        print()
        print("Invalid tools details:")
        for tool in results['invalid_tools'][:5]:
            print(f"  {tool['tool_id']}: {', '.join(tool['issues'])}")
        if len(results['invalid_tools']) > 5:
            print(f"  ... and {len(results['invalid_tools']) - 5} more")

    print()
    if results['valid_tools'] == results['total_tools']:
        print("✓ All tools are valid!")
        sys.exit(0)
    else:
        print(f"✗ {len(results['invalid_tools'])} tools need attention")
        sys.exit(1)


if __name__ == "__main__":
    main()


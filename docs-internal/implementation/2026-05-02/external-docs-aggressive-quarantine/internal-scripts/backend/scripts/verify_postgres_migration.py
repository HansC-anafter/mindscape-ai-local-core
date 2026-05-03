#!/usr/bin/env python3
"""
PostgreSQL System Verification Runner
=====================================
Unified entry script for executing verification tests at various levels of the PostgreSQL architecture.
This is a persistent Developer Tool.

Usage:
    python scripts/verify_postgres_migration.py [--scope SCOPE] [--group GROUP]

Examples:
    python scripts/verify_postgres_migration.py --scope=infra
    python scripts/verify_postgres_migration.py --scope=caps --group=ig
    python scripts/verify_postgres_migration.py --scope=all
"""

import argparse
import sys
import subprocess
import os
from pathlib import Path

# Add backend to sys.path
BACKEND_DIR = Path(__file__).parent.parent
sys.path.append(str(BACKEND_DIR))


def run_pytest(test_path: str, markers: str = None):
    """Execute Pytest"""
    cmd = [sys.executable, "-m", "pytest", test_path, "-v"]
    if markers:
        cmd.extend(["-m", markers])

    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(BACKEND_DIR))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="PostgreSQL System Verification Tool")
    parser.add_argument(
        "--scope",
        type=str,
        choices=["infra", "caps", "integrity", "all"],
        default="all",
        help="Verification Scope (infra=Infrastructure, caps=Capabilities, integrity=System Integrity)",
    )
    parser.add_argument(
        "--group",
        type=str,
        choices=["ig", "identity", "ops", "lens"],
        help="Specific Capability Group to verify (Only for 'caps' scope)",
    )

    args = parser.parse_args()

    base_test_dir = "tests/migration/postgres"

    print("=" * 60)
    print("🐘 Mindscape Local-Core PostgreSQL System Verification")
    print("=" * 60)

    # 1. Infrastructure Layer
    if args.scope in ["infra", "all"]:
        print("\n[Layer: Infrastructure] Verifying Adapters & Connections...")
        code = run_pytest(f"{base_test_dir}/infrastructure")
        if code != 0:
            print("❌ Infrastructure Verification Failed!")
            sys.exit(code)
        print("✅ Infrastructure Verified")

    # 2. Capability Layer
    if args.scope in ["caps", "all"]:
        print("\n[Layer: Capabilities] Verifying Business Logic...")

        groups = [args.group] if args.group else ["ig", "identity", "ops", "lens"]

        group_map = {
            "ig": "test_pack_ig.py",
            "identity": "test_core_identity.py",
            "ops": "test_core_ops.py",
            "lens": "test_lens.py",
        }

        for g in groups:
            test_file = group_map.get(g)
            if test_file:
                print(f"  > Verifying Capability: {g}...")
                # Check if file exists before running, to allow partial implementation
                full_path = BACKEND_DIR / base_test_dir / "capabilities" / test_file
                if full_path.exists():
                    code = run_pytest(f"{base_test_dir}/capabilities/{test_file}")
                    if code != 0:
                        print(f"❌ Capability {g} Failed!")
                        sys.exit(code)
                else:
                    print(f"  ⚠️ Skipping {g} (Test file not found: {test_file})")

        print("✅ Capabilities Verified")

    # 3. System Integrity
    if args.scope in ["integrity", "all"]:
        print("\n[Layer: Integrity] Verifying System Constraints...")
        code = run_pytest(f"{base_test_dir}/integrity")
        if code != 0:
            print("❌ Integrity Check Failed!")
            sys.exit(code)
        print("✅ Integrity Verified")

    print("\n" + "=" * 60)
    print("🎉 All Verification Scopes Passed Successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()

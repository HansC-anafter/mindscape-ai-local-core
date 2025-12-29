#!/usr/bin/env python3
"""
Validate code comments against developer guidelines.

Rules:
1. No Chinese comments in implementation code
2. No implementation steps/records
3. No non-functional descriptions
4. No emojis
"""

import re
import sys
from pathlib import Path
import subprocess

# Patterns to check
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')
STEP_PATTERN = re.compile(r'(Step\s+\d+|步驟|TODO|FIXME|XXX|HACK|NOTE:|FIXED|Fixed|Added|Removed|Changed|Updated|記錄|紀錄)')
NON_FUNCTIONAL_PATTERN = re.compile(r'(important|重要|don.t forget|別忘記|temporary|臨時|temp|暫時|This is|這是)')
EMOJI_PATTERN = re.compile(r'[✅❌⚠️🚀💡🔧📝🎯🔥💯⭐️🌟]')

def check_file(file_path: Path) -> list:
    """Check a single file for comment violations."""
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Error reading {file_path}: {e}"]

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Check for comment lines (Python: #, TypeScript/JavaScript: //)
        is_comment = False
        comment_content = ""

        if stripped.startswith('#'):
            is_comment = True
            comment_content = stripped[1:].strip()
        elif '//' in line:
            # Extract content after //
            parts = line.split('//', 1)
            if len(parts) > 1:
                is_comment = True
                comment_content = parts[1].strip()

        if is_comment and comment_content:
            # Check Chinese
            if CHINESE_PATTERN.search(comment_content):
                violations.append(f"{file_path}:{line_num} - Chinese comment found: {stripped}")

            # Check implementation steps/records
            if STEP_PATTERN.search(comment_content, re.IGNORECASE):
                violations.append(f"{file_path}:{line_num} - Implementation step/record found: {stripped}")

            # Check non-functional descriptions
            if NON_FUNCTIONAL_PATTERN.search(comment_content, re.IGNORECASE):
                violations.append(f"{file_path}:{line_num} - Non-functional description found: {stripped}")

            # Check emojis
            if EMOJI_PATTERN.search(comment_content):
                violations.append(f"{file_path}:{line_num} - Emoji found: {stripped}")

    return violations

def get_changed_files():
    """Get changed files from git."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'origin/master...HEAD'],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            # Try alternative: check unstaged changes
            result = subprocess.run(
                ['git', 'diff', '--name-only'],
                capture_output=True,
                text=True,
                check=False
            )

        changed_files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
        return changed_files
    except Exception as e:
        print(f"Warning: Could not get changed files from git: {e}")
        return []

def main():
    """Main validation function."""
    # Get changed files from git
    changed_files = get_changed_files()

    # Filter code files
    code_extensions = {'.py', '.ts', '.tsx', '.js', '.jsx'}
    code_files = [
        Path(f) for f in changed_files
        if Path(f).suffix in code_extensions and Path(f).exists()
    ]

    # If no changed files, check all files in current directory
    if not code_files:
        print("No changed code files found. Checking current directory...")
        workspace_root = Path(__file__).parent.parent
        for ext in code_extensions:
            code_files.extend(workspace_root.rglob(f'*{ext}'))

        # Exclude common directories
        excluded_dirs = {'node_modules', '.git', '__pycache__', 'venv', '.venv', 'dist', 'build'}
        code_files = [f for f in code_files if not any(excluded in str(f) for excluded in excluded_dirs)]

    if not code_files:
        print("No code files to check.")
        return 0

    print(f"Checking {len(code_files)} file(s)...\n")

    all_violations = []
    for file_path in code_files:
        violations = check_file(file_path)
        all_violations.extend(violations)

    if all_violations:
        print("❌ Code comment violations found:\n")
        for violation in all_violations:
            print(f"  {violation}")
        print("\nPlease fix these violations before committing.")
        print("\nSee: docs-internal/implementation/architecture-refactoring-2025-12-22/CODE_COMMENT_VALIDATION_CHECKLIST.md")
        return 1
    else:
        print("✅ All code comments comply with guidelines.")
        return 0

if __name__ == "__main__":
    sys.exit(main())








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
STEP_PATTERN = re.compile(r'(Step\s+\d+|\u6b65\u9a5f|TODO|FIXME|XXX|HACK|NOTE:|FIXED|Fixed|Added|Removed|Changed|Updated|\u8a18\u9304|\u7d00\u9304)')
NON_FUNCTIONAL_PATTERN = re.compile(
    r'(\bimportant\b|\u91cd\u8981|don.t forget|\u5225\u5fd8\u8a18|\btemporary\b|\u81e8\u6642|\btemp\b|\u66ab\u6642|\bThis is\b|\u9019\u662f)'
)
EMOJI_PATTERN = re.compile(
    r'[\u2705\u274c\u26a0\ufe0f\U0001f680\U0001f4a1\U0001f527\U0001f4dd\U0001f3af\U0001f525\U0001f4af\u2b50\U0001f31f]'
)

def _extract_python_comment(line: str, multiline_quote: str | None) -> tuple[str | None, str]:
    """Return Python line comment content outside string literals."""
    i = 0
    quote: str | None = None
    escaped = False

    while i < len(line):
        if multiline_quote:
            end = line.find(multiline_quote, i)
            if end == -1:
                return multiline_quote, ""
            i = end + 3
            multiline_quote = None
            continue

        char = line[i]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            i += 1
            continue

        if line.startswith('"""', i) or line.startswith("'''", i):
            marker = line[i : i + 3]
            end = line.find(marker, i + 3)
            if end == -1:
                multiline_quote = marker
                return multiline_quote, ""
            i = end + 3
            continue

        if char in {"'", '"'}:
            quote = char
            i += 1
            continue

        if char == "#":
            return multiline_quote, line[i + 1 :].strip()

        i += 1

    return multiline_quote, ""

def _extract_slash_comment(line: str) -> str:
    """Return JavaScript/TypeScript line comment content outside string literals."""
    quote: str | None = None
    escaped = False
    i = 0

    while i < len(line) - 1:
        char = line[i]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            i += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            i += 1
            continue

        if char == "/" and line[i + 1] == "/":
            return line[i + 2 :].strip()

        i += 1

    return ""

def check_file(file_path: Path) -> list:
    """Check a single file for comment violations."""
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Error reading {file_path}: {e}"]

    python_multiline_quote = None
    is_python = file_path.suffix == '.py'
    is_slash_comment_file = file_path.suffix in {'.ts', '.tsx', '.js', '.jsx'}

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        comment_content = ""
        if is_python:
            python_multiline_quote, comment_content = _extract_python_comment(
                line,
                python_multiline_quote,
            )
        elif is_slash_comment_file:
            comment_content = _extract_slash_comment(line)

        if comment_content:
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
        print("Code comment violations found:\n")
        for violation in all_violations:
            print(f"  {violation}")
        print("\nPlease fix these violations before committing.")
        print("\nReview the public contribution and code comment rules before committing.")
        return 1
    else:
        print("All code comments comply with guidelines.")
        return 0

if __name__ == "__main__":
    sys.exit(main())




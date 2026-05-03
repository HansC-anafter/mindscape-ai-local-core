---
description: How to search for files in hidden directories (e.g. .agent/, .gemini/)
---

# Searching Hidden Directories

## Problem

`find_by_name` uses `fd` which **ignores hidden directories** (`.agent/`, `.gemini/`, etc.) by default.
There is no way to pass `--hidden` flag through `find_by_name`.

## Solution

**ALWAYS use `run_command` with `find` when searching for files that might be in hidden directories:**

```bash
// turbo
find <search_path> -maxdepth <depth> -type f -name "<pattern>" 2>/dev/null | head -20
```

## When to Use

- Searching for skills (`.agent/skills/`)
- Searching for workflows (`.agent/workflows/`)
- Searching for any file under a `.` prefixed directory
- When `find_by_name` returns 0 results but you suspect the file exists

## Examples

```bash
# Find a skill
// turbo
find /Users/shock/Projects_local/workspace -maxdepth 6 -path "*skills/*" -name "SKILL.md" -type f 2>/dev/null

# Find workflows
// turbo
find /Users/shock/Projects_local/workspace -maxdepth 5 -path "*workflows*" -name "*.md" -type f 2>/dev/null
```

#!/bin/bash
# CI Script: Check for hardcoded capability brand words in core pages
# This script prevents hardcoding capability-specific logic in Shell/Host core pages

set -e

# Capability brand words to check (case-insensitive)
BRAND_WORDS=(
  "site-hub"
  "site_hub"
  "Site-Hub"
  "SiteHub"
  "wordpress"
  "WordPress"
  "wp"
  "WP"
  "instagram"
  "Instagram"
  "ig"
  "IG"
  "grant.*scout"
  "Grant.*Scout"
  "yogacoach"
  "YogaCoach"
)

# Directories to check (core pages)
CORE_DIRS=(
  "web-console/src/app/settings"
  "web-console/src/app/workspaces"
  "packages/shell/src"
)

# Directories to exclude (capability-specific code is allowed here)
EXCLUDE_DIRS=(
  "web-console/src/app/capabilities"
  "**/node_modules"
  "**/.next"
)

# Build exclude pattern
EXCLUDE_PATTERN=""
for dir in "${EXCLUDE_DIRS[@]}"; do
  EXCLUDE_PATTERN="${EXCLUDE_PATTERN} --exclude-dir=${dir}"
done

# Track violations
VIOLATIONS=0
VIOLATION_FILES=()

echo "🔍 Checking for hardcoded capability brand words in core pages..."
echo ""

# Check each core directory
for core_dir in "${CORE_DIRS[@]}"; do
  if [ ! -d "$core_dir" ]; then
    echo "⚠️  Directory not found: $core_dir (skipping)"
    continue
  fi

  echo "Checking: $core_dir"

  # Check each brand word
  for brand_word in "${BRAND_WORDS[@]}"; do
    # Use grep to find matches (case-insensitive)
    matches=$(grep -r -i -l --include="*.tsx" --include="*.ts" "$brand_word" "$core_dir" $EXCLUDE_PATTERN 2>/dev/null || true)

    if [ -n "$matches" ]; then
      echo "  ❌ Found '$brand_word' in:"
      echo "$matches" | while read -r file; do
        echo "     - $file"
        VIOLATION_FILES+=("$file")
        VIOLATIONS=$((VIOLATIONS + 1))
      done
    fi
  done
done

echo ""

# Report results
if [ $VIOLATIONS -eq 0 ]; then
  echo "✅ No hardcoded capability brand words found in core pages"
  exit 0
else
  echo "❌ Found $VIOLATIONS violation(s) of capability brand word policy"
  echo ""
  echo "Violations found in:"
  printf '%s\n' "${VIOLATION_FILES[@]}" | sort -u | while read -r file; do
    echo "  - $file"
  done
  echo ""
  echo "💡 Solution: Use Capability Slot mechanism instead of hardcoding"
  echo "   See: docs-internal/SHELL_EXTRACTION_IMPLEMENTATION_PLAN_2026-01-05.md"
  exit 1
fi


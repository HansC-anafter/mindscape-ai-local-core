# CapabilityInstaller Guard - Preventing Direct Commits

This document describes the engineering safeguards to prevent committing files that should be installed via CapabilityInstaller.

## Overview

Certain files should be installed via `CapabilityInstaller` rather than committed directly to the repository:

- **Feature-specific playbooks** (e.g., Sonic Space, Yoga Coach)
- **Feature-specific models** (e.g., `sonic_space/`, `yogacoach/`)
- **Capability files** (already protected by `.gitignore`)

## Protection Mechanisms

### 1. `.gitignore` Rules

The `.gitignore` file includes patterns to exclude:

```gitignore
# Feature-specific playbooks
/backend/playbooks/specs/sonic_*.json
/backend/playbooks/specs/yoga_*.json
/backend/i18n/playbooks/**/yoga_*.md
/backend/i18n/playbooks/**/sonic_*.md

# Feature-specific models
/backend/app/models/sonic_space/
/backend/app/models/yogacoach/

# Capability files
/backend/app/capabilities/
/web-console/src/app/capabilities/
```

**Note**: System playbooks (e.g., `cis_*`, `grant_scout`, `ig_*`) can be committed as they are core functionality.

### 2. Pre-commit Hook

The `.git/hooks/pre-commit` hook checks staged files before commit:

- Blocks commits containing feature-specific playbooks
- Blocks commits containing feature-specific models
- Blocks commits containing capability files
- Provides clear error messages with instructions

**Location**: `.git/hooks/pre-commit`

**How it works**:
1. Scans all staged files
2. Matches against protected patterns
3. Blocks commit if violations found
4. Provides unstage instructions

### 3. Pre-push Hook

The `.git/hooks/pre-push` hook checks commits before pushing:

- Scans all commits being pushed
- Detects any protected files in commit history
- Blocks push if violations found
- Provides revert instructions

**Location**: `.git/hooks/pre-push`

**How it works**:
1. Examines all commits in the push range
2. Checks file paths in each commit
3. Blocks push if protected files detected
4. Provides history cleanup instructions

### 4. CI/CD Checks (Recommended)

Add GitHub Actions or similar CI checks:

```yaml
# .github/workflows/check-capability-files.yml
name: Check Capability Files
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Check for protected files
        run: |
          if git diff --name-only origin/main...HEAD | grep -E "backend/playbooks/specs/(sonic_|yoga_)|backend/app/models/(sonic_space|yogacoach)/"; then
            echo "❌ Error: Protected files detected"
            exit 1
          fi
```

## What Can Be Committed

### ✅ Allowed

- **System playbooks**: `cis_*`, `grant_scout`, `ig_*` (core functionality)
- **Core models**: All models in `backend/app/models/` except feature-specific ones
- **Core code**: All application code, routes, services
- **Configuration**: Docker, package.json, etc.

### ❌ Blocked

- **Feature-specific playbooks**: `sonic_*.json`, `yoga_*.json`
- **Feature-specific i18n**: `yoga_*.md`, `sonic_*.md` in i18n directories
- **Feature-specific models**: `sonic_space/`, `yogacoach/`
- **Capability files**: Anything in `backend/app/capabilities/` or `web-console/src/app/capabilities/`

## Installation via CapabilityInstaller

To install feature-specific content:

```bash
# Install a capability pack
python -m backend.app.services.capability_installer install <pack-file.mindpack>

# The installer will:
# 1. Extract playbook specs to backend/playbooks/specs/
# 2. Extract i18n files to backend/i18n/playbooks/
# 3. Install models to backend/app/models/
# 4. Install tools and services to backend/app/capabilities/
# 5. Install UI components to web-console/src/app/capabilities/
```

## Troubleshooting

### Hook Not Working

If hooks are not executing:

1. Check permissions: `chmod +x .git/hooks/pre-commit .git/hooks/pre-push`
2. Verify hook exists: `ls -la .git/hooks/pre-commit`
3. Test manually: `.git/hooks/pre-commit`

### Bypassing Hooks (Not Recommended)

If you must bypass (e.g., for emergency fixes):

```bash
# Skip pre-commit hook
git commit --no-verify -m "message"

# Skip pre-push hook
git push --no-verify
```

**Warning**: Only use `--no-verify` in exceptional circumstances. Always review what you're committing.

### Updating Protected Patterns

To add new protected patterns:

1. Update `.gitignore` with new patterns
2. Update `.git/hooks/pre-commit` with new checks
3. Update `.git/hooks/pre-push` with new checks
4. Update this documentation

## Best Practices

1. **Always use CapabilityInstaller** for feature-specific content
2. **Test hooks locally** before pushing
3. **Review staged files** with `git status` before committing
4. **Keep system playbooks** in the repository (they're core functionality)
5. **Document exceptions** if any protected files need to be committed

## Related Documentation

- [CapabilityInstaller Service](../backend/app/services/capability_installer.py)
- [Adapter Compilation Guide](./adapter-compilation-guide.md)
- [Playbook Development Guide](../playbook-development/getting-started.md)


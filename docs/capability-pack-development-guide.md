# Capability Pack Development Guide

This guide explains how to develop and install capability packs for Mindscape AI Local Core.

> **[IMPORTANT] Portability Contract**
> All capabilities must comply with the [Capability Portability Contract](./capability-portability-contract.md) to ensure they can run in both Cloud and Local-Core environments. The contract is enforced by CI, and any non-compliant PR will be blocked.

## Overview

A capability pack is a self-contained bundle that extends Mindscape AI with new functionality. Each pack includes:

- Playbooks (workflow definitions)
- Tools (executable functions)
- Services (background services)
- Bootstrap scripts (initialization hooks)

## Standard Pack Structure

```text
your-capability-pack/
├── manifest.yaml          # Pack metadata and configuration
├── README.md              # Installation, usage, and requirements
├── playbooks/
│   ├── specs/             # JSON playbook definitions
│   └── {locale}/          # Markdown playbook descriptions
├── tools/                 # Python tool implementations
├── services/              # Python service implementations
└── scripts/               # Bootstrap and utility scripts (optional)
```

## Manifest Structure

The `manifest.yaml` file defines the pack's metadata and configuration:

```yaml
code: your_pack_code
display_name: "Your Pack Name"
version: "1.0.0"
type: feature
description: "Brief description of the pack"

# Playbooks provided by this pack
playbooks:
  - code: your_playbook_code
    locales: [zh-TW, en]
    path: playbooks/{locale}/your_playbook.md
    spec_path: playbooks/specs/your_playbook.json
    tool_dependencies:
      - core_llm.structured_extract
      - your_custom_tool
    service_dependencies: []

# Bootstrap hooks (post-install initialization)
bootstrap:
  - type: content_vault_init
    vault_path: null  # null = use default (~/content-vault)

  # Or use custom Python script
  - type: python_script
    path: scripts/bootstrap.py
    timeout: 60

# Environment variables required
env:
  - CONTENT_VAULT_PATH  # Optional, defaults to ~/content-vault
  - YOUR_API_KEY        # Required for this pack
```

## Bootstrap Hooks

Bootstrap hooks are executed automatically after pack installation. They handle initialization tasks like:

- Creating directory structures
- Setting up configuration files
- Initializing external resources

### Hook Types

#### 1. Content Vault Initialization

Automatically initializes Content Vault directory structure:

```yaml
bootstrap:
  - type: content_vault_init
    vault_path: null  # Use default path (~/content-vault)
```

This hook:

- Creates vault directory structure (`series/`, `arcs/`, `posts/`, etc.)
- Creates `.vault-config.yaml` configuration file
- Copies template files to `assets/templates/`

#### 2. Custom Python Script

Execute a custom Python script:

```yaml
bootstrap:
  - type: python_script
    path: scripts/bootstrap.py
    timeout: 60  # Optional, default: 60 seconds
```

The script should:

- Be executable from the pack root directory
- Exit with code 0 on success
- Handle errors gracefully (log warnings, don't crash)

### Automatic Bootstrap for Known Packs

Some capability codes automatically trigger bootstrap hooks:

```python
# In capability_installer.py
ig_related_codes = [
    'ig_post', 'ig_post_generation', 'instagram', 'social_media',
    'ig_series_manager', 'ig_review_system'
]
```

**Important**: This whitelist is a fallback mechanism. **Always declare bootstrap in your manifest.yaml** for clarity and maintainability.

**Priority Order**:

1. **Highest**: Explicit `bootstrap` configuration in `manifest.yaml`
2. **Fallback**: Capability code matching whitelist (for backward compatibility)

**⚠️ Important**: Don't rely on whitelist matching. Always include `bootstrap` in your manifest:

```yaml
bootstrap:
  - type: content_vault_init
    vault_path: null
```

**Why this matters**:
- The whitelist is hardcoded and may not include your pack's code
- If your pack code doesn't match the whitelist pattern, Content Vault won't auto-initialize
- Explicit `bootstrap` configuration ensures your pack works regardless of whitelist changes

**Current whitelist** (for reference only):
- `ig_post`, `ig_post_generation`, `instagram`, `social_media`
- `ig_series_manager`, `ig_review_system`

**If you're creating a new IG-related pack**:
1. ✅ **Recommended**: Add `bootstrap` to your manifest.yaml (always works)
2. ⚠️ **Alternative**: Ensure your pack code matches the whitelist pattern (fragile)
3. 🔧 **If missed**: Manually run `python backend/scripts/init_content_vault.py` after installation

## Environment Variables

### Content Vault Path

The Content Vault path can be configured via environment variable:

```bash
export CONTENT_VAULT_PATH=/custom/path/to/vault
```

**Default**: `~/content-vault`

**Fallback behavior**:

- If `CONTENT_VAULT_PATH` is not set, uses `~/content-vault`
- If vault doesn't exist, automatically initializes on first startup
- If vault exists but subdirectories are missing, automatically creates them on startup
- The system always verifies vault structure completeness on startup, even if vault already exists

### Application Startup Initialization

On application startup, the system automatically checks for Content Vault:

1. Checks `CONTENT_VAULT_PATH` environment variable or uses default path
2. If vault doesn't exist or `.vault-config.yaml` is missing, automatically initializes
3. If initialization fails, logs warning but does not block startup

## Manual Initialization

You can manually initialize Content Vault using the initialization script:

```bash
# Use default path (~/content-vault)
python backend/scripts/init_content_vault.py

# Specify custom path
python backend/scripts/init_content_vault.py --vault-path /custom/path

# Force recreation (overwrites existing)
python backend/scripts/init_content_vault.py --force
```

## Pack Installation Flow

1. **Extract**: Unpack `.mindpack` file to temporary directory
2. **Validate**: Validate `manifest.yaml` structure
3. **Install**: Copy playbooks, tools, services to target directories
4. **Bootstrap**: Execute bootstrap hooks (if defined)
5. **Register**: Update capability registry

### Bootstrap Execution

Bootstrap hooks are executed in order:

- If a hook fails, it logs a warning but continues with remaining hooks
- Timeout errors are logged but don't block installation
- Script execution errors are logged but don't block installation

**Important**: Bootstrap failures do not prevent pack installation. The pack will be installed, but initialization may be incomplete.

## Development Workflow

### 1. Create Pack Structure

```bash
mkdir -p your-pack/{playbooks/{specs,zh-TW,en},tools,services,scripts}
```

### 2. Write Manifest

Create `manifest.yaml` with pack metadata and bootstrap hooks:

```yaml
code: your_pack
display_name: "Your Pack"
version: "1.0.0"
description: "Description"

playbooks:
  - code: your_playbook
    locales: [en]
    path: playbooks/{locale}/your_playbook.md
    spec_path: playbooks/specs/your_playbook.json

bootstrap:
  - type: content_vault_init
    vault_path: null
```

### 3. Create Bootstrap Script (Optional)

If you need custom initialization:

```python
#!/usr/bin/env python3
# scripts/bootstrap.py

import sys
from pathlib import Path

def main():
    # Your initialization logic
    vault_path = Path.home() / "content-vault"
    # Create directories, config files, etc.
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### 4. Write README

Include in `README.md`:

- Installation instructions
- Environment variable requirements
- Bootstrap behavior
- Manual initialization steps (if needed)
- Testing instructions

### 5. Test Installation

```bash
# Package your pack
tar -czf your-pack.mindpack your-pack/

# Install via API or CLI
# Verify bootstrap hooks executed correctly
# Check logs for warnings
```

## Best Practices

### 1. Idempotent Bootstrap

Bootstrap scripts should be idempotent (safe to run multiple times):

```python
# Good: Check if already initialized
if vault_path.exists() and not force:
    if all_subdirs_exist(vault_path):
        return  # Already initialized
    else:
        create_missing_dirs(vault_path)  # Repair missing directories
```

### 2. Graceful Failure

Bootstrap failures should not block installation:

```python
# Good: Log warning, continue
try:
    initialize_resource()
except Exception as e:
    logger.warning(f"Bootstrap failed: {e}")
    # Don't raise - installation continues
```

### 3. Environment Variable Documentation

Document all required environment variables in `README.md`:

```markdown
## Environment Variables

- `CONTENT_VAULT_PATH`: Path to content vault (default: ~/content-vault)
- `YOUR_API_KEY`: Required API key for this pack
```

### 4. Path Configuration

Use environment variables for paths, avoid hardcoding:

```python
# Good
vault_path = os.getenv("CONTENT_VAULT_PATH") or Path.home() / "content-vault"

# Bad
vault_path = Path("/hardcoded/path")
```

### 5. Testing Bootstrap

Include tests for bootstrap scripts:

```python
# tests/test_bootstrap.py
def test_bootstrap_creates_structure():
    with tempfile.TemporaryDirectory() as tmpdir:
        bootstrap.main(tmpdir)
        assert (tmpdir / "series").exists()
        assert (tmpdir / ".vault-config.yaml").exists()
```

## Example: IG Pack

The IG (Instagram) pack demonstrates these patterns:

**Manifest** (`backend/app/capabilities/ig/manifest.yaml`):

- Defines multiple playbooks
- Uses automatic bootstrap (via capability code matching)

**Bootstrap Behavior**:

- Automatically initializes Content Vault on installation
- Creates directory structure for IG posts
- Sets up templates

**Environment**:

- Uses `CONTENT_VAULT_PATH` (defaults to `~/content-vault`)
- Falls back gracefully if vault initialization fails

## Troubleshooting

### Bootstrap Not Running

1. Check `manifest.yaml` has `bootstrap` section
2. Verify capability code matches automatic bootstrap patterns
3. Check installation logs for bootstrap execution

### Initialization Fails

1. Check `CONTENT_VAULT_PATH` is set correctly
2. Verify write permissions to vault directory
3. Check logs for specific error messages
4. Try manual initialization: `python backend/scripts/init_content_vault.py`

### Missing Directories

If vault exists but subdirectories are missing:

- The system automatically repairs missing directories on startup
- Or run: `python backend/scripts/init_content_vault.py` (without `--force`)

## Related Documentation

- [Playbook Development Guide](./playbook-development/README.md)
- [Tool Development Guide](./contributor-guide/README.md)
- Internal: `docs-internal/implementation/architecture-refactoring-2025-12-24/CONTENT_VAULT_BOOTSTRAP.md`

# Capability Portability Contract

**Version**: 1.0.0
**Date**: 2026-01-03
**Status**: Active - Enforced by CI

> **[IMPORTANT]**
> This contract is enforced as a CI Gate. Any PR that does not comply with this contract will be blocked by CI and cannot be merged.

---

## Overview

This contract defines the standards for developing capabilities that can run seamlessly in both Cloud and Local-Core environments. All capabilities must comply with these requirements to ensure portability and maintainability.

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [P0: Environment Abstraction Layer](#p0-environment-abstraction-layer)
3. [P1: Optional Dependencies & Degradation Strategy](#p1-optional-dependencies--degradation-strategy)
4. [P2: Unified Directory & Routing Standards](#p2-unified-directory--routing-standards)
5. [P3: Manifest Schema v2](#p3-manifest-schema-v2)
6. [P4: Dependency Injection Adapter Layer](#p4-dependency-injection-adapter-layer)
7. [P5: CI/CD Validation Gates](#p5-cicd-validation-gates)
8. [P6: Startup Validation](#p6-startup-validation)
9. [Release Gates](#release-gates)
10. [Migration Guide](#migration-guide)

---

## Core Principles

### 1. Single Entry Point

All capability internal imports must use a unified prefix:

```python
# [CORRECT] Only allowed format
from mindscape.capabilities.yogacoach.tools import intake_router
from mindscape.capabilities.yogacoach.services import pipeline_orchestrator

# [FORBIDDEN] CI will block
from capabilities.yogacoach.tools import intake_router
from backend.app.capabilities.yogacoach.tools import intake_router
import capabilities  # Bare module import also forbidden
from capabilities import yogacoach  # Bare module import also forbidden
```

**Important**: The import validation uses a **blacklist mechanism**, only prohibiting environment-specific import paths (`capabilities.*` and `backend.app.capabilities.*`). Standard library and third-party imports are still allowed.

### 2. Explicit over Implicit

All environment-specific dependencies must be explicitly declared in the manifest:

```yaml
dependencies:
  required:
    - core_llm
  optional:
    - name: contracts.execution_context
      fallback: mindscape.shims.execution_context
      degraded_features:
        - pipeline_orchestration
```

### 3. Graceful Degradation

When optional dependencies are unavailable, the capability must be able to start, but related features are marked as `degraded`.

### 4. Validation First

All validation is completed before merge/release, not discovered at runtime.

---

## P0: Environment Abstraction Layer

The environment abstraction layer automatically handles path differences between Cloud and Local-Core environments. All capability code must use the `from mindscape.capabilities.xxx import yyy` format.

**Environment Detection Priority** (from highest to lowest):

1. `MINDSCAPE_ENVIRONMENT` environment variable (explicit specification)
2. `MINDSCAPE_CAPABILITIES_ROOT` environment variable (explicit root directory)
3. `/app/capabilities` (Cloud container environment)
4. `/app/backend/app/capabilities` (Local-Core container environment)
5. `capabilities/` in current directory (development environment, Cloud mode)
6. `backend/app/capabilities/` in current directory (development environment, Local-Core mode)

**Implementation**: `mindscape/__init__.py`

---

## P1: Optional Dependencies & Degradation Strategy

All capabilities must declare dependencies in `manifest.yaml`:

```yaml
dependencies:
  required:
    - core_llm
  optional:
    - name: contracts.execution_context
      fallback: mindscape.shims.execution_context
      degraded_features:
        - pipeline_orchestration
```

When optional dependencies are unavailable, the capability can start but related features are marked as `degraded`.

---

## P2: Unified Directory & Routing Standards

**[IMPORTANT] Prefix responsibility must be clear to avoid duplicate prefix issues**

**Standard: Option A (Enforced, only standard)**

- Capability routers **must NOT** set `prefix` parameter
- Capability paths use relative paths (e.g., `/sessions`, `/upload`)
- Prefix is entirely determined by `manifest.yaml`'s `apis[].prefix`
- Installer/Registry is responsible for adding prefix when mounting

**Validation Rules (CI enforced)**:
- Router definitions must not contain `prefix=` parameter (only for capability's `api/` directory)
- `apis[].prefix` in manifest is a required field

**Directory Structure Standard**:

```
capability_code/
├── manifest.yaml              # Required: Capability pack declaration
├── __init__.py                # Required: Python package initialization
├── api/                       # ⚠️ Standard API directory (preferred)
│   ├── __init__.py
│   └── {endpoint_name}.py
├── routes/                    # ❌ Deprecated, migrate to api/
├── tools/                     # Tool implementations
├── services/                  # Service implementations
└── playbooks/                 # Playbook definitions
```

**Example Router Definition**:

```python
# api/__init__.py
from fastapi import APIRouter

# [CORRECT] No prefix parameter
router = APIRouter(tags=["yogacoach"])

# Sub-routes (also no prefix)
from .intake import router as intake_router
from .upload import router as upload_router

router.include_router(intake_router)
router.include_router(upload_router)
```

**Manifest Configuration**:

```yaml
apis:
  - code: yogacoach
    path: api/__init__.py
    router_export: router
    prefix: /yogacoach      # [REQUIRED] Only source of prefix
    enabled_by_default: true
```

---

## P3: Manifest Schema v2

**Required Fields**:
- `code`: Capability unique identifier
- `version`: Semantic version number
- `portability`: Portability declaration (required)

**Portability Declaration Format**:

```yaml
portability:
  min_local_core_version: "0.9.0"
  environments:
    - cloud
    - local-core
  degradation_strategy: graceful
```

**Tool Definition Format** (must use `mindscape.capabilities.*` format):

```yaml
tools:
  - name: data_processor
    backend: "mindscape.capabilities.example_capability.tools.data_processor:process_data"
    description: "Process and analyze data"
    input_schema:
      type: object
      properties:
        # Define input fields
```

**API Definition Format**:

```yaml
apis:
  - code: example_capability
    path: api/__init__.py
    router_export: router
    prefix: /example_capability
    enabled_by_default: true
```

---

## P4: Dependency Injection Adapter Layer

Provides environment-adapted DI providers that automatically provide the correct dependency implementation based on the environment.

**Implementation Location**: `mindscape/di/providers.py` (Local-Core) or corresponding DI layer (Cloud)

**Usage Example**:

```python
from mindscape.di.providers import get_tenant_uuid, get_db_session

@router.get("/sessions")
async def list_sessions(
    tenant_uuid: str = Depends(get_tenant_uuid),
    db = Depends(get_db_session)
):
    # This route works correctly in both Cloud and Local-Core:
    # Cloud: tenant_uuid extracted from header, db connects to tenant-specific database
    # Local-Core: tenant_uuid uses default value, db connects to local SQLite
    sessions = db.query(Session).filter_by(tenant_uuid=tenant_uuid).all()
    return {"sessions": sessions}
```

---

## P5: CI/CD Validation Gates

**Validation Scripts**:
- `scripts/validate_import_paths.py`: Validates import paths
- `scripts/validate_router_prefix.py`: Validates router prefix rules
- `scripts/validate_manifest.py`: Validates manifest schema

**CI Workflow**: `.github/workflows/capability-validation.yml`

All validation steps are **Blocking** (blocking), and any step failure will cause the PR to be unable to merge.

---

## P6: Startup Validation

Validates at application startup to ensure:
1. No route conflicts
2. No illegal imports
3. All required dependencies are available

**Implementation Location**: `mindscape/startup/validators.py`

---

## Release Gates

| Gate | Description | Validation Method | Blocking Level |
|------|-------------|-------------------|----------------|
| Import Paths | All imports use `mindscape.capabilities.*` | CI Script | Block |
| Manifest Schema | manifest.yaml conforms to schema | CI Script | Block |
| Portability Declaration | Contains portability field and supports local-core | CI Script | Block |
| Route Conflicts | No duplicate routes | Startup Validation | Block |
| Required Dependencies | All required dependencies available | Startup Validation | Block |
| Tool Backend | Tool backend uses `mindscape.capabilities.*` format | CI Script | Block |

---

## Migration Guide

### Migrating from Existing Capability

```bash
# 1. Update import paths
find capabilities/example_capability -name "*.py" -exec sed -i '' \
  's/from capabilities\./from mindscape.capabilities./g' {} \;

find capabilities/example_capability -name "*.py" -exec sed -i '' \
  's/from backend\.app\.capabilities\./from mindscape.capabilities./g' {} \;

# 2. Update manifest.yaml
# Add portability field
# Update tool backend paths to mindscape.capabilities.* format

# 3. Move routes/ to api/
mv capabilities/example_capability/routes capabilities/example_capability/api

# 4. Update router definitions (remove prefix parameter)
# In api/__init__.py, remove prefix parameter from APIRouter(...)

# 5. Run validation
python scripts/validate_manifest.py capabilities/example_capability
python scripts/validate_import_paths.py capabilities/example_capability
python scripts/validate_router_prefix.py capabilities/example_capability
```

### Migration Checklist

```markdown
## Migration Checklist for {capability_code}

### Phase 1: Import Paths
- [ ] Replace all `from capabilities.` with `from mindscape.capabilities.`
- [ ] Replace all `from backend.app.capabilities.` with `from mindscape.capabilities.`
- [ ] Run `validate_import_paths.py` to confirm

### Phase 2: Manifest Update
- [ ] Add `portability` field
- [ ] Update tool `backend` path format to `mindscape.capabilities.*`
- [ ] Add `dependencies.optional` declarations
- [ ] Run `validate_manifest.py` to confirm

### Phase 3: Directory Structure
- [ ] Move `routes/` to `api/` (if exists)
- [ ] Update `apis[].path` to `api/xxx.py`
- [ ] Confirm router prefix does not conflict

### Phase 4: Dependency Handling
- [ ] Identify cloud-only dependencies
- [ ] Create shim or mark degradation for each cloud-only dependency
- [ ] Update manifest `dependencies.optional`

### Phase 5: Testing
- [ ] CI passes
- [ ] Local-Core startup test passes
- [ ] Cloud startup test passes
```

---

## Related Documentation

- [Capability Pack Development Guide](./capability-pack-development-guide.md)
- [Capability Installation Guide](../docs-internal/CAPABILITY_INSTALLATION_GUIDE.md) (Internal)
- [Developer Guide](../docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md) (Internal)

---

**Last Updated**: 2026-01-03

**Maintainer**: Mindscape AI Development Team


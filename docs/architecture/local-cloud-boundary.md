# Local/Cloud Boundary

This document explains the architectural boundary between the local-only open-source version and cloud/multi-tenant extensions.

## Core Principle

> **The core domain must never contain tenant/group concepts directly. These concepts only exist in adapters and external layers.**

## Why This Separation?

1. **Clean Open Source**: The open-source version remains simple and focused
2. **Easy Extension**: Cloud features can be added without modifying core code
3. **Clear Boundaries**: Developers know exactly where cloud logic belongs
4. **Future-Proof**: Core remains stable while cloud features evolve

## What's in Core?

The core domain includes:

- ✅ `ExecutionContext` - Abstract execution context (`actor_id`, `workspace_id`, `tags`)
- ✅ `Port Interfaces` - `IdentityPort`, `IntentRegistryPort`
- ✅ `Services` - Intent extraction, playbook execution, conversation orchestration
- ✅ `Models` - Workspace, tasks, timeline items (no tenant/group fields)
- ✅ `Local Adapters` - `LocalIdentityAdapter`, `LocalIntentRegistryAdapter`

## What's NOT in Core?

The core domain explicitly excludes:

- ❌ `Tenant` or `Group` types/classes
- ❌ Direct references to `tenant_id` or `group_id` in core code
- ❌ Cloud-specific clients (`SiteHubClient`, `CrsClient`)
- ❌ Multi-tenant business logic
- ❌ Cloud deployment configurations

## How Cloud Extensions Work

Cloud extensions work by:

1. **Implementing Ports**: Cloud adapters implement the same Port interfaces
2. **Injecting Context**: Cloud adapters populate `ExecutionContext.tags` with cloud-specific data
3. **External Services**: Cloud logic lives in separate repositories/services

### Example: Cloud Identity Adapter

```python
# In cloud repository (not in open-source core)
class SiteHubIdentityAdapter(IdentityPort):
    async def get_current_context(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> ExecutionContext:
        # Extract from JWT token (cloud-specific)
        token = get_auth_token()
        payload = decode_jwt(token)

        # Return ExecutionContext with cloud data in tags
        return ExecutionContext(
            actor_id=payload.user_id,
            workspace_id=payload.workspace_id,
            tags={
                "mode": "cloud",
                "tenant_id": payload.tenant_id,  # Cloud data in tags
                "group_id": payload.group_id,
                "plan": payload.plan_tier
            }
        )
```

The core never sees `tenant_id` directly - it only sees `tags`, which it treats as an opaque key-value dictionary.

## ExecutionContext.tags

The `tags` field in `ExecutionContext` is the bridge between local and cloud:

- **Local**: `tags = {"mode": "local"}`
- **Cloud**: `tags = {"mode": "cloud", "tenant_id": "...", "group_id": "..."}`

Core services don't interpret `tags` - they just pass it through. Adapters and external services can read/write `tags` as needed.

## Repository Structure

### Open Source Repository (This Repo)

```
mindscape-local-core/
├── backend/app/
│   ├── core/              # ExecutionContext, Ports
│   ├── adapters/local/    # Local adapters only
│   ├── services/          # Core services (use Ports)
│   └── models/            # Domain models (no tenant/group)
└── docs/                   # Public documentation
```

### Cloud Repository (Separate)

```
mindscape-cloud/
├── adapters/cloud/         # Cloud adapters
│   ├── site_hub_identity_adapter.py
│   └── crs_intent_registry_adapter.py
├── clients/                # Cloud service clients
│   ├── site_hub_client.py
│   └── crs_client.py
└── services/cloud/         # Cloud-specific services
    ├── tenant_management.py
    └── billing.py
```

## Migration Path

If you want to add cloud features:

1. **Don't modify core**: Keep core clean
2. **Create cloud repo**: Separate repository for cloud code
3. **Implement adapters**: Create cloud adapters that implement Ports
4. **Inject at runtime**: Use dependency injection to switch adapters

## Enforcement

To maintain this boundary:

1. **Code Review**: Reject PRs that add tenant/group to core
2. **Linting**: Add rules to detect tenant/group in core files
3. **Documentation**: Keep this document updated
4. **Testing**: Ensure core tests don't depend on cloud concepts

## Related Documentation

- [Port Architecture](./port-architecture.md) - How Ports enable this separation
- [ExecutionContext](./execution-context.md) - ExecutionContext usage guide

---

**Last updated:** 2025-12-01


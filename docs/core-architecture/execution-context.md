# ExecutionContext

`ExecutionContext` is the core abstraction for execution context in Mindscape AI. It provides a unified way to represent "who is doing what, where" without exposing cloud-specific concepts like tenant or group.

## Overview

```python
from app.core.execution_context import ExecutionContext

ctx = ExecutionContext(
    actor_id="local-user",
    workspace_id="default",
    tags={"mode": "local"}
)
```

## Properties

### actor_id

The entity performing the action. In local mode, this is typically `"local-user"`. In cloud mode, this would be the user ID from authentication.

**Replaces**: `profile_id` in core domain code.

### workspace_id

The workspace where the action occurs. In local mode, this is typically `"default"`. In cloud mode, this would be the workspace ID from the request.

### tags

Optional key-value dictionary for additional context. This is where cloud-specific data (like `tenant_id`, `group_id`) can be stored without polluting the core domain.

**Important**: Core services don't interpret `tags` - they just pass it through. Adapters and external services can read/write `tags` as needed.

## Usage Examples

### Creating ExecutionContext

```python
from app.core.execution_context import ExecutionContext

# Local mode
ctx = ExecutionContext(
    actor_id="local-user",
    workspace_id="default",
    tags={"mode": "local"}
)

# Cloud mode (in adapter)
ctx = ExecutionContext(
    actor_id=user_id,
    workspace_id=workspace_id,
    tags={
        "mode": "cloud",
        "tenant_id": tenant_id,
        "group_id": group_id,
        "plan": "premium"
    }
)
```

### Using ExecutionContext in Services

```python
class IntentExtractor:
    async def extract_and_create_timeline_item(
        self,
        ctx: ExecutionContext,
        message: str,
        message_id: str
    ) -> Optional[TimelineItem]:
        # Use ctx.actor_id instead of profile_id
        # Use ctx.workspace_id instead of workspace_id parameter

        result = await self.intent_registry.resolve_intent(
            user_input=message,
            ctx=ctx,  # Pass entire context
            ...
        )

        # Create timeline item using context
        timeline_item = TimelineItem(
            workspace_id=ctx.workspace_id,
            ...
        )
```

### Getting ExecutionContext from IdentityPort

```python
class ConversationOrchestrator:
    def __init__(self, identity_port: IdentityPort):
        self.identity_port = identity_port

    async def route_message(
        self,
        workspace_id: str,
        profile_id: str,
        ...
    ):
        # Get context through Port
        ctx = await self.identity_port.get_current_context(
            workspace_id=workspace_id,
            profile_id=profile_id
        )

        # Use context in core services
        await self.intent_extractor.extract_and_create_timeline_item(
            ctx=ctx,
            ...
        )
```

## Tags Usage

### Local Mode Tags

```python
tags = {
    "mode": "local"
}
```

### Cloud Mode Tags (Example)

```python
tags = {
    "mode": "cloud",
    "tenant_id": "tenant-123",
    "group_id": "group-456",
    "plan": "premium",
    "region": "us-west-2"
}
```

### Reading Tags (in Adapters/External Services)

```python
# In cloud adapter
if ctx.tags and ctx.tags.get("mode") == "cloud":
    tenant_id = ctx.tags.get("tenant_id")
    # Use tenant_id for cloud-specific logic
```

**Note**: Core services should NOT read or interpret `tags`. They should only pass it through.

## Best Practices

1. **Always use ExecutionContext**: Don't pass `profile_id` and `workspace_id` separately
2. **Don't interpret tags in core**: Core services should treat `tags` as opaque
3. **Use IdentityPort**: Get context through `IdentityPort`, not by creating it directly
4. **Pass context down**: Pass `ExecutionContext` to downstream services, don't extract fields

## Migration from profile_id/workspace_id

### Before (Old Pattern)

```python
async def some_method(
    self,
    workspace_id: str,
    profile_id: str,
    ...
):
    # Use workspace_id and profile_id directly
    workspace = self.store.get_workspace(workspace_id)
    user = self.store.get_user(profile_id)
```

### After (New Pattern)

```python
async def some_method(
    self,
    ctx: ExecutionContext,
    ...
):
    # Use ctx.workspace_id and ctx.actor_id
    workspace = self.store.get_workspace(ctx.workspace_id)
    user = self.store.get_user(ctx.actor_id)
```

## Four-Layer Model

The Execution Context four-layer model provides a conceptual framework for understanding how different aspects of execution context are organized:

1. **Task / Goal** (What to do) - Task boundaries, input/output specifications
2. **Policy / Constraints** (What cannot be done) - Constraints and consistency rules
3. **Lens / Perspective** (How to do it) - Attention allocation, trade-offs, narrative path
4. **Assets / Memory** (What materials to use) - Data materials, workspace metadata, artifact references

The `mind_lens` field in ExecutionContext contains resolved lens values (Layer 3), while `tags` can contain metadata for Policy (Layer 2) and Assets (Layer 4).

**Core Principle**: Task remains unchanged, Lens can be swapped; Policy is fixed to maintain bottom line; Assets provide materials.

See [Execution Context Four-Layer Model](./execution-context-four-layer-model.md) for detailed conceptual mapping.

## Integration with Mind Lens

The `mind_lens` field integrates with the Mind Lens system:

```python
from app.services.lens.mind_lens_service import MindLensService

service = MindLensService()

# Resolve lens for execution context
resolved = service.resolve_lens(
    user_id="user_123",
    workspace_id="workspace_001",
    role_hint="writer"
)

# Use in execution context
ctx = ExecutionContext(
    actor_id="user_123",
    workspace_id="workspace_001",
    mind_lens=resolved.values if resolved else None
)
```

The resolved lens values influence how tasks are interpreted and executed. See [Mind Lens Architecture](./mind-lens.md) for details.

## Integration with Lens Composition

For multi-lens scenarios, use Lens Composition:

```python
from app.services.lens.composition_service import CompositionService
from app.services.lens.fusion_service import FusionService

composition_service = CompositionService()
fusion_service = FusionService()

# Get and fuse composition
composition = composition_service.get_composition("comp_001")
fused = fusion_service.fuse_composition(composition, lens_instances)

# Use fused context
ctx = ExecutionContext(
    actor_id="user_123",
    workspace_id="workspace_001",
    mind_lens=fused.fused_values
)
```

See [Lens Composition Architecture](./lens-composition.md) for details.

## Related Documentation

- [Execution Context Four-Layer Model](./execution-context-four-layer-model.md) - Conceptual framework for execution context layers
- [Mind Lens Architecture](./mind-lens.md) - Mind Lens core architecture
- [Lens Composition Architecture](./lens-composition.md) - Multi-lens combination
- [Port Architecture](./port-architecture.md) - How ExecutionContext fits into Port pattern
- [Local/Cloud Boundary](./local-cloud-boundary.md) - Why ExecutionContext doesn't contain tenant/group

---

**Last updated:** 2025-12-22


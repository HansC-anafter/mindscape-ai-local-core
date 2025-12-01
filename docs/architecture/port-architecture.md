# Port Architecture

This document describes the Port/Adapter pattern used in Mindscape AI Local Core, which enables clean separation between the core domain and external integrations.

## Overview

The Port/Adapter pattern (also known as Hexagonal Architecture) allows the core domain to remain independent of external concerns. In Mindscape AI Local Core, this pattern is used to:

- Keep the core domain clean and free of cloud/tenant-specific concepts
- Enable future cloud extensions without modifying core code
- Support different identity and intent resolution strategies

## Core Principles

1. **Core domain only knows abstractions**: The core never directly depends on concrete implementations
2. **Adapters implement Ports**: External integrations are implemented as adapters that conform to Port interfaces
3. **Dependency injection**: Ports are injected into core services, not instantiated directly

## Port Interfaces

### IdentityPort

The `IdentityPort` interface provides execution context for the core domain:

```python
from app.core.ports.identity_port import IdentityPort
from app.core.execution_context import ExecutionContext

class IdentityPort(ABC):
    @abstractmethod
    async def get_current_context(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> ExecutionContext:
        pass
```

**Purpose**: Get the current execution context without the core knowing how identity is determined.

**Local Implementation**: `LocalIdentityAdapter` returns a fixed context for single-user mode.

**Future Cloud Implementation**: Would extract identity from JWT tokens, session data, etc.

### IntentRegistryPort

The `IntentRegistryPort` interface resolves user input into structured intents:

```python
from app.core.ports.intent_registry_port import IntentRegistryPort, IntentResolutionResult

class IntentRegistryPort(ABC):
    @abstractmethod
    async def resolve_intent(
        self,
        user_input: str,
        ctx: ExecutionContext,
        context: Optional[str] = None,
        locale: Optional[str] = None
    ) -> IntentResolutionResult:
        pass

    @abstractmethod
    async def list_available_intents(
        self,
        ctx: ExecutionContext
    ) -> List[IntentDefinition]:
        pass
```

**Purpose**: Resolve user input to intents without the core knowing where intent definitions come from.

**Local Implementation**: `LocalIntentRegistryAdapter` wraps the existing LLM-based intent extractor.

**Future Cloud Implementation**: Would query cloud intent registry services, filter by tenant, etc.

## ExecutionContext

The `ExecutionContext` is the core abstraction for execution context:

```python
from app.core.execution_context import ExecutionContext

ctx = ExecutionContext(
    actor_id="local-user",
    workspace_id="default",
    tags={"mode": "local"}
)
```

**Key Properties**:
- `actor_id`: The entity performing the action (replaces `profile_id` in core)
- `workspace_id`: The workspace where the action occurs
- `tags`: Optional key-value dictionary for additional context (tenant, group, plan, etc.)

**Important**: The core domain never sees `tenant_id` or `group_id` directly. These concepts only exist in `tags` and are interpreted by adapters.

## Architecture Flow

```
┌─────────────────────────────────────────┐
│         Web Console (UI)                │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│      API Routes (FastAPI)                │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   Services (via Ports)                  │
│   - IntentExtractor                     │
│   - ExecutionCoordinator                │
│   - ConversationOrchestrator            │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   Port Interfaces                       │
│   - IdentityPort                        │
│   - IntentRegistryPort                  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   Local Adapters                        │
│   - LocalIdentityAdapter                │
│   - LocalIntentRegistryAdapter          │
└─────────────────────────────────────────┘
```

## Usage Example

### In ConversationOrchestrator

```python
class ConversationOrchestrator:
    def __init__(
        self,
        identity_port: Optional[IdentityPort] = None,
        intent_registry: Optional[IntentRegistryPort] = None
    ):
        # Auto-create local adapters if not provided
        if identity_port is None:
            identity_port = LocalIdentityAdapter()
        if intent_registry is None:
            intent_registry = LocalIntentRegistryAdapter()

        self.identity_port = identity_port
        self.intent_registry = intent_registry

    async def route_message(self, workspace_id: str, profile_id: str, ...):
        # Get execution context through Port
        ctx = await self.identity_port.get_current_context(
            workspace_id=workspace_id,
            profile_id=profile_id
        )

        # Use context in core services
        timeline_item = await self.intent_extractor.extract_and_create_timeline_item(
            ctx=ctx,
            message=message,
            ...
        )
```

### In IntentExtractor

```python
class IntentExtractor:
    def __init__(self, intent_registry: IntentRegistryPort, ...):
        self.intent_registry = intent_registry

    async def extract_and_create_timeline_item(
        self,
        ctx: ExecutionContext,
        message: str,
        ...
    ):
        # Resolve intent through Port
        result = await self.intent_registry.resolve_intent(
            user_input=message,
            ctx=ctx,
            context=context_str,
            locale=locale
        )

        # Use result (core doesn't know where it came from)
        intents_list = result.intents
        themes_list = result.themes
```

## Benefits

1. **Clean Core**: Core domain has no knowledge of cloud/tenant concepts
2. **Easy Extension**: Add cloud adapters without touching core code
3. **Testability**: Easy to mock Ports for testing
4. **Flexibility**: Switch between local and cloud implementations at runtime

## Future Extensions

To add cloud support:

1. Create cloud adapters in a separate repository:
   - `SiteHubIdentityAdapter` - Extracts identity from JWT tokens
   - `CrsIntentRegistryAdapter` - Queries cloud intent registry

2. Inject cloud adapters in cloud deployment:
   ```python
   identity_port = SiteHubIdentityAdapter(site_hub_endpoint)
   intent_registry = CrsIntentRegistryAdapter(crs_endpoint)
   orchestrator = ConversationOrchestrator(
       identity_port=identity_port,
       intent_registry=intent_registry
   )
   ```

3. Core code remains unchanged.

## Related Documentation

- [Local/Cloud Boundary](./local-cloud-boundary.md) - Why we separate local and cloud
- [ExecutionContext](./execution-context.md) - ExecutionContext usage guide

---

**Last updated:** 2025-12-01


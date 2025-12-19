# Governance Decision & Risk Control Layer

> This document describes the **Governance Decision & Risk Control Layer** architecture in Mindscape AI, which sits between the Intent Governance Layer and the Playbook Execution Layer, providing multi-layered governance checks and risk control before and during playbook execution.

**Last Updated**: 2025-12-19
**Status**: Architecture Design Document
**Version**: v1.0

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Position](#architecture-position)
3. [Core Components](#core-components)
4. [Data Flow](#data-flow)
5. [Event Contracts](#event-contracts)
6. [API Interfaces](#api-interfaces)
7. [Implementation Reference](#implementation-reference)

---

## Overview

The **Governance Decision & Risk Control Layer** is a critical architectural layer that ensures safe, controlled, and compliant execution of playbooks in Mindscape AI. It provides:

1. **Pre-execution Governance Checks**: Multi-layered governance decisions before playbook execution
2. **Risk Control**: Risk assessment and mitigation during execution
3. **Decision Recording**: Audit trail of all governance decisions
4. **User Decision Support**: Interactive decision cards for user approval when needed

### Key Design Principles

- **Layered Governance**: Multiple independent governance layers (Node, Preflight)
- **Unified Decision**: Single coordinator aggregates all governance layer results
- **Event-Driven**: All governance decisions are published as events for observability
- **Local-First**: All governance mechanisms work in local environments

---

## Architecture Position

### Layer Hierarchy

```
┌─────────────────────────────────────────┐
│     Intent Governance Layer              │
│  (IntentCard, IntentCluster)            │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Governance Decision & Risk Control     │
│  ┌─────────────────────────────────────┐ │
│  │  Node Governance                     │ │
│  │  Playbook Preflight                 │ │
│  └─────────────────────────────────────┘ │
│  ┌─────────────────────────────────────┐ │
│  │  Unified Decision Coordinator       │ │
│  └─────────────────────────────────────┘ │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│     Playbook Execution Layer             │
│  (PlaybookRunner, Sandbox)               │
└─────────────────────────────────────────┘
```

### Integration Points

- **Upstream**: Intent Governance Layer (receives execution requests)
- **Downstream**: Playbook Execution Layer (controls execution permission)
- **Lateral**: Event System (publishes governance events), Execution Coordinator (orchestrates checks)

---

## Core Components

### 1. Governance Services

The layer consists of two independent governance services, each responsible for a specific aspect of risk control:

#### 1.1 Node Governance

**Purpose**: Controls which playbooks can be executed based on allowlists, blocklists, and risk labels.

**Responsibilities**:
- **Playbook allowlist/blocklist**: Explicit allow/deny lists for playbook execution
- **Risk label checking**: Validates required risk labels (e.g., `requires_repo_access`, `requires_api_key`)
- **Simple throttling**: Rate limiting for write operations (count or frequency limits)

**Configuration**:
- Stored in `SystemSettingsStore` under `governance.node_governance`
- Playbook allowlist/blocklist per workspace
- Risk label definitions and requirements
- Throttling thresholds (write operation count or frequency limits)

#### 1.2 Playbook Preflight

**Purpose**: Validates playbook inputs, environment, and prerequisites before execution.

**Responsibilities**:
- **Required input validation**: Checks that all required inputs are provided
- **Environment/credential verification**: Validates existence of:
  - Sandbox paths
  - Repository access
  - API keys
  - Required tools
- **Prerequisite checks**: Ensures all prerequisites are met before execution

**Return States**:
- **`pass`**: All checks passed, execution can proceed
- **`need_clarification`**: Missing inputs or unclear requirements, user action needed
- **`reject`**: Critical failures (e.g., missing credentials, invalid environment)

**Configuration**:
- Stored in `SystemSettingsStore` under `governance.preflight`
- Required input definitions per playbook
- Environment validation rules
- Credential requirements

### 2. Governance Mode

**Purpose**: Controls how governance violations are handled.

**Modes**:
- **`strict_mode`**: Blocks execution on any governance violation
- **`warning_mode`**: Shows warnings but allows execution to proceed

**Configuration**:
- Stored in `SystemSettingsStore` under `governance.mode`
- Mutually exclusive: only one mode can be active at a time
- Default: `warning_mode = True`, `strict_mode = False`

### 3. Unified Decision Coordinator

**Purpose**: Orchestrates all governance services and produces a unified decision.

**Responsibilities**:
- Invokes all governance services in parallel
- Aggregates governance layer results
- Applies governance mode (strict vs warning)
- Generates `UnifiedDecisionResult`
- Publishes governance decision events to event stream

**Decision Logic**:
- **All Pass**: Execution proceeds
- **Any Fail + strict_mode**: Execution blocked, `DECISION_REQUIRED` event with `rejected` status
- **Any Fail + warning_mode**: Execution proceeds with warnings, `DECISION_REQUIRED` event with `warning` status
- **need_clarification**: Execution blocked, `DECISION_REQUIRED` event with `pending` status, user action required

---

## Data Flow

### Pre-Execution Governance Check Flow

```
Playbook Execution Request
    ↓
UnifiedDecisionCoordinator.check()
    ↓
┌─────────────────────────────────────┐
│  Parallel Governance Service Calls  │
│  ├─ NodeGovernance.check()         │
│  └─ PlaybookPreflight.check()      │
└─────────────────────────────────────┘
    ↓
Collect All Layer Results
    ↓
Generate UnifiedDecisionResult
    ↓
┌─────────────────────────────────────┐
│  Decision Processing                 │
│  ├─ All Pass → Allow Execution      │
│  ├─ Any Fail → Send Decision Card   │
│  └─ Warnings → Log & Allow         │
└─────────────────────────────────────┘
    ↓
Publish Governance Event
    ↓
Return Decision to Execution Coordinator
```

### Decision Result States

| State | Description | Action |
|-------|-------------|--------|
| **approved** | All governance layers passed | Execution proceeds |
| **rejected** | One or more layers failed | Execution blocked, decision card shown |
| **pending** | User decision required | Wait for user approval/rejection |

---

## Event Contracts

### Governance Decision Event

All governance decisions are published as `DECISION_REQUIRED` events to the event stream. The event payload contains `governance_decision` data for frontend cards and status indicators.

**Event Type**: `DECISION_REQUIRED`

**Event Structure**:
```typescript
interface GovernanceDecisionEvent {
  event_type: "DECISION_REQUIRED";
  timestamp: string;
  execution_id: string;
  workspace_id: string;
  playbook_code: string;
  payload: {
    governance_decision: {
      decision_id: string;
      status: "pending" | "approved" | "rejected" | "warning";
      layers: {
        node_governance?: {
          status: "pass" | "fail" | "warning";
          reason?: string;
          blocked_by_blacklist?: boolean;
          risk_label_required?: string[];
        };
        playbook_preflight?: {
          status: "pass" | "fail" | "warning" | "need_clarification";
          reason?: string;
          missing_inputs?: string[];
          validation_errors?: string[];
        };
      };
      requires_user_decision: boolean;
      mode: "strict" | "warning";
    };
  };
}
```

### Event Flow Integration

- **Event Publisher**: `UnifiedDecisionCoordinator` publishes `DECISION_REQUIRED` events after decision
- **Event Subscriber**: UI components subscribe to events to show decision cards and status indicators
- **Event Store**: Events stored in SQLite `events` table for audit trail
- **Decision History**: Query governance decisions via existing `/api/v1/workspaces/{workspace_id}/events` API (no additional database tables needed)

---

## API Interfaces

### Governance Service Interface

All governance services implement a common interface:

```python
class GovernanceService(ABC):
    """Base interface for governance services"""

    @abstractmethod
    async def check(
        self,
        execution_context: ExecutionContext,
        playbook_code: str,
        playbook_inputs: Dict[str, Any],
        **kwargs
    ) -> GovernanceLayerResult:
        """
        Execute governance check

        Args:
            execution_context: Execution context with workspace/user info
            playbook_code: Playbook identifier
            playbook_inputs: Playbook input parameters
            **kwargs: Additional parameters

        Returns:
            GovernanceLayerResult: Layer-specific decision result
        """
        pass
```

### Unified Decision Coordinator API

```python
class UnifiedDecisionCoordinator:
    """Unified decision coordinator"""

    async def check(
        self,
        execution_context: ExecutionContext,
        playbook_code: str,
        playbook_inputs: Dict[str, Any]
    ) -> UnifiedDecisionResult:
        """
        Execute all governance layer checks

        Returns:
            UnifiedDecisionResult: Aggregated decision result
        """
        pass
```

### REST API Endpoints

#### Governance Configuration API

**Base Path**: `/api/v1/system-settings/governance/`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/node-governance` | GET/PUT | Node governance configuration |
| `/preflight` | GET/PUT | Playbook preflight configuration |
| `/mode` | GET/PUT | Governance mode toggle |

#### Governance Status API

**Base Path**: `/api/v1/workspaces/{workspace_id}/governance/`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Current governance status |

---

## Implementation Reference

### Core Implementation Paths

**Governance Services**: `backend/app/services/governance/`
- `node_governance.py`
- `playbook_preflight.py`

**Decision Coordinator**: `backend/app/services/governance/unified_decision_coordinator.py`

**API Routes**:
- `backend/app/routes/core/workspace_governance.py`
- `backend/app/routes/core/system_settings/governance.py`

### Data Models

**Unified Decision Result**:
```python
class UnifiedDecisionResult(BaseModel):
    """Unified governance decision result"""
    decision_id: str
    execution_id: str
    workspace_id: str
    playbook_code: str
    overall_status: Literal["approved", "rejected", "pending"]
    layers: Dict[str, GovernanceLayerResult]
    requires_user_decision: bool
    timestamp: datetime
```

**Governance Layer Result**:
```python
class GovernanceLayerResult(BaseModel):
    """Single governance layer decision result"""
    layer_name: str  # "node_governance", "playbook_preflight"
    status: Literal["pass", "fail", "warning", "need_clarification"]
    reason: Optional[str]
    metadata: Dict[str, Any]  # Layer-specific metadata (e.g., missing_inputs, risk_labels)
```

**Governance Mode Settings**:
```python
class GovernanceModeSettings(BaseModel):
    """Governance mode settings stored in SystemSettingsStore"""
    strict_mode: bool = False  # Block execution on violations
    warning_mode: bool = True   # Show warnings but allow execution
```

**Storage**: All governance settings stored in `SystemSettingsStore`:
- `governance.node_governance`: Node governance configuration
- `governance.preflight`: Preflight configuration
- `governance.mode`: Mode settings (strict_mode, warning_mode)

### Frontend Integration

**Decision Card Components**: `web-console/src/components/workspace/governance/`
- `GovernanceDecisionCard.tsx`
- `NodeGovernanceRejectedCard.tsx`
- `PreflightFailedCard.tsx`

**Configuration UI**: `web-console/src/app/settings/components/GovernancePanel.tsx`

---

## Related Documentation

### Architecture Documents

- [System Overview](./system-overview.md) - Complete system architecture
- [Memory & Intent Architecture](./memory-intent-architecture.md) - Intent Governance Layer
- [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md) - Playbook execution layer

---

## Summary

The **Governance Decision & Risk Control Layer** provides a minimal governance framework for local-core single-machine scenarios, ensuring safe and controlled playbook execution in Mindscape AI.

### Core Components

1. **Node Governance**: Playbook allowlist/blocklist, risk label checking (e.g., `requires_repo_access`), simple throttling (write operation count/frequency)
2. **Playbook Preflight**: Required input validation, environment/credential verification (sandbox/repo/API key existence), returns `need_clarification` or `reject` on failures
3. **Governance Mode**: `strict_mode` (block) or `warning_mode` (warn but allow), configured via `SystemSettingsStore`
4. **Event Output**: `DECISION_REQUIRED` events with `governance_decision` payload for frontend cards/status indicators; decision history queryable via existing events API (no additional database tables)

### Design Principles

- **Minimal Dependencies**: All settings stored in `SystemSettingsStore`, no additional database tables
- **Event-Driven**: Governance decisions published as events, queryable via existing events API
- **Local-First**: No cloud-specific features (cost governance, policy service, multi-tenant features omitted or stubbed)

**Key Takeaways**:
- Node Governance: Allowlist/blocklist, risk labels, simple throttling
- Playbook Preflight: Input validation, environment/credential checks
- Governance Mode: Strict (block) or Warning (allow) modes
- Unified decision coordination across all layers
- Event-driven architecture for observability
- Settings stored in SystemSettingsStore, decisions in events table

---

**Last Updated**: 2025-12-19
**Maintainer**: Mindscape AI Development Team

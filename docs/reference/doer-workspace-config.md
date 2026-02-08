# Doer Workspace Configuration Reference

> **Version**: 1.0
> **Last Updated**: 2026-01-31
> **Status**: Reference Specification

This document defines the standard configuration for **Doer Workspaces** — isolated execution environments where external AI agents operate under Mindscape's governance layer.

---

## Overview

A **Doer Workspace** is a sandbox-isolated workspace within a workspace group, dedicated to agent-driven task execution. Other workspaces in the group handle specification, review, and operations.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Workspace Group                                  │
├──────────────────┬──────────────────┬───────────────────────────────┤
│  Spec Workspace  │  Doer Workspace  │  Review/Ops Workspace         │
│  ───────────────  │  ──────────────  │  ────────────────────         │
│  Define Intent   │  Agent Execution │  Diff Review                  │
│  Task Cards      │  Sandbox Env     │  Approve High-Risk            │
│  Constraints     │  Governed Tools  │  Promote to Pack              │
└──────────────────┴──────────────────┴───────────────────────────────┘
```

### Design Principles

1. **Execution Power Retained**: Agents can read/write files, run commands, install dependencies
2. **Boundary-Controlled**: All activity constrained to sandbox perimeter
3. **Governed Expansion**: Tool acquisition goes through approval gates
4. **Secrets Isolated**: No long-lived credentials in execution environment

---

## 1. Sandbox Policy

### 1.1 Directory Structure

```
/workspace/{workspace_id}/sandbox/
├── workspace/              # Agent working directory (read/write)
│   ├── src/
│   ├── docs/
│   └── output/
│
├── .quarantine/            # Downloaded but not activated (read/write)
│   ├── pending/            # Awaiting verification
│   └── rejected/           # Failed verification
│
├── .cache/                 # Dependency cache (read/write)
│   ├── pip/
│   ├── npm/
│   └── apt/
│
├── .mindscape/             # Mindscape metadata (read-only for agent)
│   ├── traces/             # Execution traces
│   ├── config/             # Runtime configuration
│   └── governance/         # Applied policies
│
└── .secrets/               # NOT MOUNTED to agent container
```

### 1.2 Filesystem Permissions

| Path | Agent Access | Purpose |
|------|--------------|---------|
| `workspace/` | Read/Write | Main working area |
| `.quarantine/` | Read/Write | Staged tool downloads |
| `.cache/` | Read/Write | Dependency cache |
| `.mindscape/` | Read-Only | Trace and config |
| `.secrets/` | No Access | Credentials vault |
| Host paths | No Access | System isolation |

### 1.3 Container Mount Strategy

```yaml
volumes:
  # Working area
  - ${SANDBOX_PATH}/workspace:/app/workspace:rw
  - ${SANDBOX_PATH}/.quarantine:/app/.quarantine:rw
  - ${SANDBOX_PATH}/.cache:/app/.cache:rw

  # Read-only metadata
  - ${SANDBOX_PATH}/.mindscape:/app/.mindscape:ro

  # Secrets NOT mounted - injected via governance layer
```

---

## 2. Network Policy

### 2.1 Default Egress Allowlist

```yaml
network:
  egress:
    mode: allowlist  # deny by default, allow specific hosts

    allowed_hosts:
      # Package registries
      - "pypi.org"
      - "files.pythonhosted.org"
      - "registry.npmjs.org"
      - "registry.yarnpkg.com"

      # Code repositories
      - "github.com"
      - "gitlab.com"
      - "raw.githubusercontent.com"
      - "api.github.com"

      # Container registries
      - "docker.io"
      - "ghcr.io"

      # Documentation
      - "docs.python.org"
      - "developer.mozilla.org"

      # AI providers (if approved)
      - "api.anthropic.com"
      - "api.openai.com"

    denied_hosts:
      - "*.internal"
      - "10.*"
      - "192.168.*"
      - "172.16.*"

    # Rate limiting
    rate_limit:
      requests_per_minute: 60
      bandwidth_mbps: 10
```

### 2.2 Per-Intent Override

Intents can request additional hosts:

```yaml
# In Intent definition
network_permissions:
  additional_hosts:
    - "api.stripe.com"      # Requires approval
  justification: "Payment integration testing"
```

---

## 3. Tool Acquisition Policy

### 3.1 Two-Stage Process

```
Stage 1: ACQUIRE                   Stage 2: PROMOTE
─────────────────                  ─────────────────
• Download allowed                 • Governance approval required
• Into .quarantine/ only           • Verify signature/checksum
• No execution permitted           • Check permission requirements
• Agent can explore freely         • Decision Card generated
```

### 3.2 Acquire Stage

Agent can freely:
- Search package registries
- Clone repositories (to `.quarantine/`)
- Download binaries (to `.quarantine/`)

```python
# Acquire stage - no governance required
quarantine_path = sandbox / ".quarantine" / "pending" / tool_name
await agent.download(source_url, quarantine_path)
```

### 3.3 Promote Stage

Activation requires governance:

```yaml
# Tool activation request (generated by agent)
tool_activation_request:
  tool_name: "voice-synthesis-lib"
  source: "https://github.com/user/voice-lib"
  quarantine_path: ".quarantine/pending/voice-synthesis-lib"

  required_permissions:
    filesystem: ["workspace/*"]
    network: ["api.elevenlabs.io"]
    tools: ["audio.record", "audio.play"]

  justification: "Required for voice output feature"
  estimated_risk: "medium"
```

### 3.4 Verification Flow

```python
class ToolVerifier:
    async def verify(self, request: ToolActivationRequest) -> VerificationResult:
        checks = [
            self.check_signature(request),      # Signed by trusted publisher?
            self.check_checksum(request),       # Integrity verified?
            self.check_permissions(request),    # Permissions acceptable?
            self.check_supply_chain(request),   # Dependencies clean?
        ]
        return await asyncio.gather(*checks)
```

### 3.5 Decision Card

```yaml
# Generated for human review (high-risk) or auto-approve (trusted)
decision_card:
  id: "tool-activate-2026-01-31-001"
  type: "tool_activation"

  tool:
    name: "voice-synthesis-lib"
    version: "1.2.0"
    publisher: "verified-publisher"

  permissions_requested:
    - type: network
      scope: "api.elevenlabs.io"
      risk: low
    - type: tools
      scope: "audio.*"
      risk: medium

  verification:
    signature: "valid"
    checksum: "match"
    supply_chain: "clean"

  recommendation: "auto_approve"  # or "require_human_approval"

  auto_approve_reason: "Publisher in trusted list, permissions match policy"
```

---

## 4. Secrets Policy

### 4.1 Isolation Principle

> Secrets are **never** mounted directly into the agent container.

### 4.2 Credential Injection

Secrets are injected at the **governance layer**, not the execution layer:

```python
class SecretInjector:
    """Injects secrets into API calls without exposing to agent."""

    async def inject(self, request: APIRequest, intent: Intent) -> APIRequest:
        # Check if intent has approved access to this secret
        if not await self.governance.check_secret_access(intent, request.api):
            raise PermissionDenied("Secret access not approved")

        # Inject secret at network boundary, not in agent environment
        secret = await self.vault.get(request.api)
        request.headers["Authorization"] = f"Bearer {secret}"

        return request
```

### 4.3 Secret Access Request

```yaml
# Agent requests API access, not the secret itself
secret_access_request:
  api: "api.anthropic.com"
  purpose: "LLM inference for code generation"
  intent_id: "intent-123"

  # Agent never sees the actual token
```

### 4.4 Audit Trail

All secret access is logged:

```python
@dataclass
class SecretAccessLog:
    timestamp: datetime
    intent_id: str
    workspace_id: str
    api: str
    purpose: str
    granted: bool
    injected_by: str  # "governance_layer", not "agent"
```

---

## 5. Pack Retention Policy

### 5.1 Retention Tiers

| Tier | Retention | Use Case |
|------|-----------|----------|
| **Ephemeral** | Task duration only | One-time dependency |
| **Cached** | 7 days / until evicted | Frequently used library |
| **Resident** | Permanent | Promoted to reusable pack |

### 5.2 Promotion Flow

```
Ephemeral → Cached → Resident
    │          │          │
    │          │          └── Becomes capability pack
    │          └── Survives across tasks
    └── Deleted after task completion
```

### 5.3 Policy Configuration

```yaml
retention_policy:
  default_tier: ephemeral

  auto_cache:
    # Cache if used more than N times
    usage_threshold: 3

  promote_to_resident:
    # Requires explicit approval
    requires_approval: true
    creates_pack: true
```

---

## 6. Agent-Specific Overrides

Each agent's `AGENT.md` can override defaults:

```yaml
# agents/example_agent/AGENT.md
---
name: example_agent
inherits: doer_workspace_defaults

overrides:
  network:
    additional_hosts:
      - "api.anthropic.com"  # Agent needs LLM API access

  sandbox:
    allowed_tools:
      - file
      - web_search
      - bash  # Shell access for code execution

  retention:
    default_tier: cached  # Often reuses dependencies
---
```

---

## 7. Integration with External Agents

### 7.1 Adapter Responsibility

Each adapter must respect these policies:

```python
class BaseAgentAdapter(ABC):
    async def execute(self, request: AgentRequest) -> AgentResponse:
        # 1. Apply sandbox policy
        sandbox = await self.apply_sandbox_policy(request)

        # 2. Apply network policy
        network = await self.apply_network_policy(request)

        # 3. Execute in governed environment
        result = await self._run_agent(request, sandbox, network)

        # 4. Collect trace for audit
        trace = await self.collect_trace(result)

        return result
```

### 7.2 Policy Injection

Policies are injected at startup:

```python
adapter = ExampleAgentAdapter(
    sandbox_policy=SandboxPolicy.from_workspace(workspace),
    network_policy=NetworkPolicy.from_workspace(workspace),
    secrets_policy=SecretsPolicy.from_governance(governance),
)
```

---

## Related Documents

- [External Agents Architecture](./core-architecture/external-agents.md)
- [Governance Decision & Risk Control Layer](./core-architecture/governance-decision-risk-control-layer.md)
- [Pack Supply Chain](./core-architecture/capability-packs.md)
- [Asset Provenance](./core-architecture/asset-provenance.md)

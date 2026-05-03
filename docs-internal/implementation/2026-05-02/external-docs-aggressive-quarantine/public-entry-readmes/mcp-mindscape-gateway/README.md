# Mindscape Gateway MCP Server

Exposes Mindscape Local Core capabilities to external MCP clients (Cursor, Claude Desktop, etc.).

## Features

- **P0: Auto-Provision Workspace** - No pre-configured workspace ID required
- **P1: Mind-Lens MCP API** - Expose style adjustment capabilities
- **P2: Multi-Workspace Mode** - Per-user workspace isolation
- **P3: Context Passthrough** - Track Intent/Seed from external calls
- **P4: Chat Sync & Intent Tools** - Synchronous chat with automatic side-effects
- **P5: Sampling (Experimental)** - Server-initiated LLM calls to IDE client

## Quick Start

### Installation

```bash
npm install
npm run build
```

### Development

```bash
npm run dev
```

## Configuration

Configure via environment variables:

```bash
export MINDSCAPE_BASE_URL="http://localhost:8000"
export MINDSCAPE_API_KEY="optional-api-key"
export MINDSCAPE_PROFILE_ID="default-user"
```

### Auto-Provision (v1.1)

If `MINDSCAPE_WORKSPACE_ID` is not set, Gateway will automatically:

1. Search for existing workspace named "MCP Gateway Workspace"
2. Create a new workspace if not found

```bash
export MINDSCAPE_AUTO_PROVISION="true"                    # Enable (default)
export MINDSCAPE_DEFAULT_WORKSPACE_TITLE="My Workspace"   # Custom name
```

### Multi-Workspace Mode (v1.2)

```bash
export MINDSCAPE_GATEWAY_MODE="multi_workspace"
```

In multi_workspace mode, tools accept:

- `workspace_id` - Direct workspace ID
- `surface_user_id` - External user ID (e.g., LINE user ID)
- `surface_type` - Surface type (e.g., "line", "discord")

### Context Passthrough (v1.3)

Pass conversation context for intent/seed tracking:

```json
{
  "name": "mindscape_playbook_creative_blog_post",
  "arguments": {
    "inputs": { "topic": "yoga" },
    "_context": {
      "original_message": "Write a yoga blog post",
      "surface_type": "claude_desktop",
      "surface_user_id": "user@example.com"
    }
  }
}
```

## Tool Categories

### Tool Naming Convention

MCP protocol requires `[a-zA-Z0-9_-]` only. Tool names use underscores:

| Internal | MCP Name |
|----------|----------|
| `wordpress.get_posts` | `mindscape_tool_wordpress_get_posts` |
| `creative.blog_post` | `mindscape_playbook_creative_blog_post` |

### Mind-Lens Tools

| Tool | Description |
|------|-------------|
| `mindscape_lens_list_schemas` | List available Lens schemas |
| `mindscape_lens_resolve` | Resolve Lens for current context |
| `mindscape_lens_get_effective` | Get effective merged Lens |

### Chat Sync Tools

| Tool | Description |
|------|-------------|
| `mindscape_chat_sync` | Synchronous chat with automatic side-effects |

Supports `ide_receipts` for receipt-based override (skip hooks when IDE has already processed).

### Intent Tools

| Tool | Description |
|------|-------------|
| `mindscape_intent_extract` | Extract intent signals from text |
| `mindscape_intent_submit` | Submit intent signals to backend |

### Project Tools

| Tool | Description |
|------|-------------|
| `mindscape_project_detect` | Detect or create project context |

## Backend Integration

The gateway communicates with the MCP Bridge (`/api/v1/mcp/*`) on the backend, which provides:

- **Event Hook Service** - Idempotent side-effect execution with governance invariants
- **Receipt Validation** - IDE-provided execution receipts to skip redundant hooks
- **Sampling Gate** - Three-tier fallback: Sampling -> WS LLM -> pending card

See [MCP Gateway Architecture](../docs/core-architecture/mcp-gateway.md) for detailed design.

## Sampling (Experimental)

The server declares `experimental.sampling` capability. When the IDE client supports MCP Sampling, `server.createMessage()` sends structured prompts to the client's LLM for intent extraction, reducing WS-side LLM costs.

Safety controls: template allowlist, per-workspace rate limit (10/min), PII redaction, 30s timeout.

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mindscape": {
      "command": "/path/to/mcp-mindscape-gateway/run.sh",
      "env": {
        "MINDSCAPE_BASE_URL": "http://localhost:8200",
        "MINDSCAPE_PROFILE_ID": "default-user"
      }
    }
  }
}
```

> **Note**: `run.sh` auto-detects Node.js v18+ with ES Module support.

## Architecture

See [MCP Gateway Architecture](../docs/core-architecture/mcp-gateway.md) for detailed design.

## Documentation

- [Architecture Guide](../docs/core-architecture/mcp-gateway.md)
- [Implementation Status](./IMPLEMENTATION_STATUS.md)

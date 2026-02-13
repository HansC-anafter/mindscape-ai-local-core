# Cloud Connector Architecture

> **Platform-agnostic WebSocket bridge between Local-Core and compatible cloud platforms.**

## Overview

The Cloud Connector enables a Mindscape Local-Core instance to establish a persistent, bi-directional WebSocket connection with any cloud platform that implements the Mindscape transport protocol. This allows cloud platforms to dispatch execution requests to local-core, and local-core to report events, usage, and results back.

### Design Principles

| Principle | Description |
|-----------|-------------|
| **Platform-agnostic** | Defines a transport protocol, not a specific vendor. Any compliant platform can connect. |
| **Device identity** | Each local-core instance has a persistent device ID; authentication uses device tokens. |
| **Bi-directional** | Cloud dispatches requests to local; local reports events and results back. |
| **Graceful degradation** | If cloud connection is lost, local-core continues operating independently and reconnects automatically. |
| **Tenant isolation** | Each connection is scoped to a tenant ID, supporting multi-tenant cloud deployments. |

---

## Architecture Components

### CloudConnector (`connector.py`)

The main connection manager. Responsibilities:

- Establish and maintain WebSocket connection with automatic reconnection
- Exponential backoff for reconnection attempts
- Device token authentication
- Coordinate transport, messaging, and heartbeat handlers
- Persistent device ID management (stored in `~/.mindscape/device_id`)

### TransportHandler (`transport.py`)

Handles execution lifecycle:

- **ExecutionRequest processing**: Receives and dispatches playbook, tool, and chain execution requests from cloud
- **ExecutionEvent reporting**: Reports execution progress events back to cloud
- **UsageReport**: Reports token usage, duration, and cost estimates for metering
- **Error handling**: Reports execution errors with structured error data

### MessagingHandler (`messaging_handler.py`)

Handles messaging events from cloud-connected communication channels:

- Receives messages from cloud-connected channels (LINE, WhatsApp, etc.)
- Dispatches tasks to IDE agents via `AgentDispatchManager`
- Sends replies back through the cloud platform
- Supports workspace ID-based routing

### HeartbeatMonitor (`heartbeat.py`)

Keeps the connection alive:

- Periodic heartbeat pings
- Detects stale connections
- Triggers reconnection on heartbeat timeout

---

## Connection Flow

```text
Local-Core                        Cloud Platform
    │                                  │
    ├── GET /device-token ────────────►│  (authenticate)
    │◄── token ────────────────────────┤
    │                                  │
    ├── WebSocket connect ────────────►│  (persistent)
    │◄── execution_request ────────────┤  (cloud → local)
    ├── execution_event ──────────────►│  (local → cloud)
    ├── usage_report ─────────────────►│  (metering)
    │◄── messaging_event ──────────────┤  (channel messages)
    ├── messaging_reply ──────────────►│  (replies)
    └───────────────────────────────────┘
```

### Authentication

1. Local-core obtains a device token from the cloud platform's `/device-token` endpoint
2. The token, device ID, and tenant ID are sent in the WebSocket `connect` message
3. Cloud acknowledges with a `connect_ack` message
4. All subsequent messages are authenticated via the established session

---

## Message Types

### Cloud → Local-Core

| Message Type | Description |
|-------------|-------------|
| `connect_ack` | Connection acknowledgement |
| `execution_request` | Request to execute a playbook, tool, or chain |
| `messaging_event` | Message from a cloud-connected channel |
| `heartbeat_ack` | Heartbeat acknowledgement |

### Local-Core → Cloud

| Message Type | Description |
|-------------|-------------|
| `connect` | Initial connection with device credentials |
| `execution_event` | Execution progress/completion event |
| `usage_report` | Token usage and cost metrics |
| `messaging_reply` | Reply to a messaging event |
| `heartbeat` | Keep-alive ping |

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `CLOUD_WS_URL` | (none) | Cloud platform WebSocket URL |
| `DEVICE_ID` | (auto-generated) | Persistent device identifier |
| `TENANT_ID` | `"local"` | Tenant identifier for multi-tenant platforms |

If `CLOUD_WS_URL` is not set, the Cloud Connector is disabled and local-core operates in standalone mode.

---

## Key Code Files

| File | Description |
|------|-------------|
| `backend/app/services/cloud_connector/connector.py` | Main connector and connection management |
| `backend/app/services/cloud_connector/transport.py` | Execution request/event handling |
| `backend/app/services/cloud_connector/messaging_handler.py` | Messaging event handling |
| `backend/app/services/cloud_connector/heartbeat.py` | Heartbeat monitoring |

---

## Integration with Other Components

- **Agent WebSocket** (`/ws/agent`): MessagingHandler dispatches tasks to IDE agents via `AgentDispatchManager`
- **Capability Hot-Reload**: Cloud Connector can trigger capability reload when new packs are deployed remotely
- **Runtime Environments**: Cloud-connected runtimes appear in the Runtime Environments settings

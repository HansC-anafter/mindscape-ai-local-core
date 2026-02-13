# Runtime Environments Architecture

> **Multi-runtime management for executing playbooks and tools across local and remote backends.**

## Overview

Mindscape supports multiple runtime environments — isolated backends where playbooks and tools can execute. The default runtime is the local-core instance itself, but users can register additional runtimes (e.g., GPU servers, specialized cloud services) via the Settings UI or API.

---

## Runtime Types

| Runtime Type | Description | Registration |
|-------------|-------------|--------------|
| **Local-Core** | Built-in default runtime, always available | Automatic |
| **Cloud Runtime** | Remote runtimes connected via Cloud Connector | Via Cloud Connector auto-registration |
| **User-defined** | Custom runtimes added via Settings UI or API | Manual |

---

## Data Model

Each runtime environment has the following properties:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (`"local-core"` for built-in) |
| `name` | string | Human-readable name |
| `description` | string | Optional description |
| `icon` | string | Display icon (emoji or URL) |
| `config_url` | string | Runtime configuration endpoint URL |
| `auth_type` | string | Authentication type (`"none"`, `"api_key"`, `"oauth"`, `"token"`) |
| `auth_config` | object | Authentication configuration (encrypted at rest) |
| `status` | string | Current status (`"active"`, `"inactive"`, `"error"`) |
| `supports_dispatch` | boolean | Whether this runtime supports Dispatch Workspace |
| `supports_cell` | boolean | Whether this runtime supports Cell Workspace |
| `recommended_for_dispatch` | boolean | Preferred runtime for Dispatch operations |

---

## API Endpoints

### CRUD Operations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/runtime-environments/` | List all registered runtimes |
| `POST` | `/api/v1/runtime-environments/` | Register a new runtime |
| `GET` | `/api/v1/runtime-environments/{id}` | Get runtime details |
| `PUT` | `/api/v1/runtime-environments/{id}` | Update runtime configuration |
| `DELETE` | `/api/v1/runtime-environments/{id}` | Remove a runtime |

### Discovery

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/runtime-environments/scan` | Scan a local folder to auto-discover runtime configuration |

The scan endpoint accepts a folder path and runtime type, then automatically detects configuration files, ports, and metadata.

---

## Settings Extension Panels

Capability packs can register **settings extension panels** that appear in the Runtime Environments settings page. This is done via the `/api/v1/settings/extensions?section=runtime-environments` API.

Each extension panel can provide:
- Custom configuration UI for pack-specific runtime settings
- `showWhen` conditions to control when the panel is displayed
- Actions (buttons) that trigger pack-specific operations

---

## Frontend Integration

The Runtime Environments settings page (`/settings?tab=runtime`) displays:

1. **Built-in runtimes**: Always-visible cards for Local-Core and any auto-registered runtimes
2. **Extension panels**: Dynamically loaded UI panels from installed capability packs
3. **Add Runtime card**: UI for registering new user-defined runtimes

---

## Key Code Files

| File | Description |
|------|-------------|
| `backend/app/routes/core/runtime_environments.py` | API routes for runtime CRUD |
| `backend/app/services/runtime/runtime_auth_service.py` | Runtime authentication service |
| `backend/app/services/runtime/runtime_discovery_service.py` | Auto-discovery/scan service |
| `backend/app/routes/core/settings_extensions.py` | Settings extension panel API |
| `web-console/src/app/settings/components/RuntimeEnvironmentsSettings.tsx` | Frontend settings panel |

---

## Security

- Authentication configurations are stored with sensitive fields encrypted
- API responses strip sensitive data (API keys, tokens) by default
- Each runtime operation requires user authentication
- The built-in `local-core` runtime cannot be deleted or modified

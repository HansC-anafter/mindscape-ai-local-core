# Mindscape Device Node

Local Host Agent for Mindscape AI with MCP Server capabilities.

## Features

- **MCP Server**: Standard Model Context Protocol implementation
- **Permission Map**: YAML-based permission governance
- **Capabilities**: Filesystem, Shell, Browser automation
- **Governance Layer**: Draft/Confirm/Sandbox/Execute trust levels

## Installation

```bash
npm install
npm run build
```

### macOS (launchd)
```bash
npm run install:macos
```

### Windows (Service)
```powershell
npm run install:windows
```

## Development

```bash
npm run dev
```

## Architecture

```
Device Node
├── MCP Server (stdio/HTTP)
├── Permission Map
├── Capability Proxy
└── Governance Layer
    ├── Trust Level: read
    ├── Trust Level: draft (requires confirmation)
    ├── Trust Level: execute
    └── Trust Level: admin
```

## Configuration

Edit `config/permissions.yaml` to customize capability permissions.

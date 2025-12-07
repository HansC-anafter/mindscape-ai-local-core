# Playbook Development Guide

Welcome to the Mindscape AI Playbook Development Guide. This guide helps external developers create custom playbooks for Mindscape AI.

## Purpose

This documentation is designed for **external developers** who want to:
- Create custom playbooks that extend Mindscape AI's capabilities
- Build specialized UI interfaces for specific workflows
- Implement backend handlers for complex business logic
- Publish and share playbooks with the community

**This documentation does NOT expose internal implementation details.** It focuses on:
- How to structure a playbook repository
- How to create UI components using core-provided APIs
- How to create backend handlers using core-provided APIs
- How to publish and distribute playbooks

## Overview

Playbooks are reusable, inspectable multi-step workflows that extend Mindscape AI's capabilities. Each playbook can include:
- **Workflow Definition**: JSON-based workflow specification
- **UI Components**: React components for specialized interfaces
- **Backend Handlers**: Python handlers for complex business logic
- **Internationalization**: Multi-language support

## Quick Start

1. [Getting Started](./getting-started.md) - Create your first playbook in 5 minutes
2. [Architecture Overview](./architecture/overview.md) - Understand the playbook system architecture
3. [Examples](./examples/) - See working examples

## Documentation Structure

### Core Guides
- [Getting Started](./getting-started.md) - Quick start guide
- [Architecture Overview](./architecture/overview.md) - System architecture
- [Repository Structure](./architecture/repository-structure.md) - How to structure your playbook repo

### Frontend Development
- [Frontend Guide](./frontend/guide.md) - How to create UI components
- [Component API](./frontend/components.md) - Component API reference
- [Events](./frontend/events.md) - Event communication mechanism
- [Styling](./frontend/styling.md) - Styling and theming

### Backend Development
- [Backend Guide](./backend/guide.md) - How to create handlers
- [Resources API](./backend/resources-api.md) - Resource management API
- [Handlers](./backend/handlers.md) - Handler development guide

### Playbook Definition
- [Schema](./playbook-definition/schema.md) - JSON Schema documentation
- [Fields](./playbook-definition/fields.md) - Field descriptions
- [Best Practices](./playbook-definition/best-practices.md) - Best practices

### Examples
- [Minimal Example](./examples/minimal.md) - Minimal playbook example
- [Yearly Book](./examples/yearly-book.md) - Complete yearly book example
- [Code Snippets](./examples/snippets.md) - Useful code snippets

### Deployment
- [Publishing](./deployment/publishing.md) - How to publish your playbook
- [Versioning](./deployment/versioning.md) - Version management
- [Checklist](./deployment/checklist.md) - Publishing checklist

### API Reference
- [Frontend API](./api-reference/frontend.md) - Frontend API reference
- [Backend API](./api-reference/backend.md) - Backend API reference
- [Types](./api-reference/types.md) - TypeScript type definitions

## Key Concepts

### Playbook Structure
```
your-playbook/
├── package.json              # NPM package configuration
├── playbook/
│   ├── your_playbook.json    # Workflow definition
│   ├── your_playbook.md      # i18n (zh-TW)
│   ├── i18n/
│   │   └── en/
│   │       └── your_playbook.md
│   └── UI_LAYOUT.json        # UI layout configuration
├── components/                # React UI components
│   └── your-playbook/
│       └── YourComponent.tsx
├── backend/                   # Python handlers (optional)
│   └── handlers.py
└── src/
    └── index.ts              # Registration function
```

### Core Principles
1. **Separation**: Common components in core, playbook-specific in independent repos
2. **Dynamic Loading**: Playbooks are loaded dynamically from NPM packages
3. **Unified API**: Frontend uses unified API client, backend uses unified resource API
4. **No Direct Dependencies**: Playbooks don't depend on Local/Cloud specific implementations

## Resources

- [Architecture Documentation](./architecture/overview.md)
- [Backend API Architecture](./backend/guide.md)
- [Handler Architecture](./backend/handlers.md)
- [Example Repository](https://github.com/mindscape-ai/playbook-yearly-book)

## Support

For questions and support:
- GitHub Issues: [Create an issue](https://github.com/mindscape-ai/mindscape-ai-local-core/issues)
- Documentation: Check the [Playbook Development Documentation](./README.md)

---

**Last Updated**: 2025-12-05


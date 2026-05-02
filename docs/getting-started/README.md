# Getting Started

Use this section to install and run Mindscape AI Local Core locally.

## Recommended Path

1. [Docker Deployment Guide](./docker.md)
2. [Installation Guide](./installation.md)
3. [Platform-Specific Installation Notes](./platform-specific.md)
4. [Troubleshooting Guide](./troubleshooting.md)

Docker Compose is the supported path for most users because it starts the backend, web console, PostgreSQL, Redis, runner workers, and sidecar services with the expected ports and environment defaults.

Manual installation is intended for developers who need to run the backend or web console as local processes while providing their own database, Redis, and environment configuration.

Choose the startup path intentionally:

- Use direct Docker Compose commands when you want a container-only local stack.
- Use the platform startup helper when you also want repository-defined host companion setup before Compose starts.

Capability internals, generated runtime bundles, local data, credentials, and ignored implementation paths are not public installation material.

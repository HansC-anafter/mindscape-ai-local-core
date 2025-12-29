# Docker Deployment Guide

This guide explains how to deploy Mindscape AI Local Core using Docker and Docker Compose.

## Prerequisites

- **Docker** 20.10+ ([Install Docker](https://docs.docker.com/get-docker/))
- **Docker Compose** 2.0+ (included with Docker Desktop)
- At least **4GB RAM** available for Docker
- At least **10GB disk space** for images and volumes

## Quick Start

**You can start the system immediately after cloning - no configuration required!**

### 1. Clone the Repository

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
```

### 2. Start Services (No Configuration Needed!)

**Windows PowerShell:**
```powershell
# Change to project directory
cd mindscape-ai-local-core

# Start all services (script includes Docker health check)
.\scripts\start.ps1
```

**Linux/macOS:**
```bash
# Change to project directory
cd mindscape-ai-local-core

# Start all services (script includes Docker health check)
./scripts/start.sh
```

**Or manually:**
```bash
# Build and start all services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f
```

> **Note**: The start scripts (`start.ps1` / `start.sh`) automatically check Docker availability and provide helpful error messages if Docker Desktop is not running.

The system will start successfully **without any API keys**. You can configure API keys later through the web interface.

### 3. Access the Application

- **Frontend**: http://localhost:8300
- **Backend API**: http://localhost:8200
- **API Documentation**: http://localhost:8200/docs

> **💡 Important**: API keys (OpenAI or Anthropic) are **optional** for initial startup. The system will start successfully without them, and you can configure them later through the web interface at http://localhost:8300/settings. Some AI features will be unavailable until API keys are configured.

### 4. Configure API Keys (Optional)

> **Note**: You can configure API keys through the web interface after starting services. Creating a `.env` file is optional but recommended for production use.

To configure via `.env` file, create it in the project root:

```bash
# LLM Providers (at least one required)
OPENAI_API_KEY=your_openai_api_key_here
# or
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Database
DATABASE_URL=sqlite:///./data/mindscape.db

# PostgreSQL (optional, for vector storage)
POSTGRES_DB=mindscape_vectors
POSTGRES_USER=mindscape
POSTGRES_PASSWORD=mindscape_password

# Security
LOCAL_AUTH_SECRET=dev-secret-key-change-in-production

# Logging
LOG_LEVEL=INFO

# OCR Service
OCR_USE_GPU=false
OCR_LANG=ch

# Timezone
TZ=UTC
```


## Services

The Docker Compose configuration includes:

1. **backend** - FastAPI backend service (port 8200)
2. **frontend** - Next.js web console (port 8300, mapped from container port 3000)
3. **postgres** - PostgreSQL with pgvector for vector storage (port 5433, mapped from container port 5432)
4. **ocr-service** - PaddleOCR service for PDF processing (port 8001)

## Common Commands

### Start Services

```bash
# Start all services in detached mode
docker compose up -d

# Start specific service
docker compose up -d backend
```

### Stop Services

```bash
# Stop all services
docker compose stop

# Stop and remove containers
docker compose down

# Stop and remove containers + volumes (⚠️ deletes data)
docker compose down -v
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f ocr-service
```

### Rebuild Services

```bash
# Rebuild all services
docker compose build

# Rebuild specific service
docker compose build backend

# Rebuild and restart
docker compose up -d --build
```

### Access Container Shell

```bash
# Backend container
docker compose exec backend bash

# Frontend container
docker compose exec frontend sh

# PostgreSQL container
docker compose exec postgres psql -U mindscape -d mindscape_vectors
```

## Data Persistence

Data is persisted in Docker volumes:

- **PostgreSQL data**: `postgres_data` volume
- **Application data**: `./data` directory (mounted from host)
- **Logs**: `./logs` directory (mounted from host)

To backup data:

```bash
# Backup PostgreSQL
docker compose exec postgres pg_dump -U mindscape mindscape_vectors > backup.sql

# Backup application data
tar -czf data-backup.tar.gz ./data
```

## Development Mode

The Docker Compose configuration is set up for development:

- **Hot reload** enabled for backend and frontend
- **Source code mounted** as volumes for live updates
- **Development mode** enabled for better debugging

For production deployment, modify the Dockerfiles to use production builds.

## Troubleshooting

### Port Already in Use

If ports 3000, 8000, 8001, or 5432 are already in use:

1. Stop the conflicting service, or
2. Modify port mappings in `docker-compose.yml`:

```yaml
ports:
  - "3001:3000"  # Change frontend port
  - "8001:8000"  # Change backend port
```

### Container Won't Start

```bash
# Check logs
docker compose logs backend

# Check container status
docker compose ps

# Restart service
docker compose restart backend
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check PostgreSQL logs
docker compose logs postgres

# Test connection
docker compose exec backend python -c "import psycopg2; print('OK')"
```

### OCR Service Issues

```bash
# Check OCR service logs
docker compose logs ocr-service

# Test OCR health endpoint
curl http://localhost:8001/health
```

### Out of Memory

If containers are killed due to memory issues:

1. Increase Docker memory limit in Docker Desktop settings
2. Reduce number of services (e.g., disable OCR if not needed)
3. Use `docker compose up` without `-d` to see error messages

## Production Considerations

For production deployment:

1. **Set strong passwords** in `.env` file
2. **Use production builds** (modify Dockerfiles)
3. **Enable HTTPS** (use reverse proxy like nginx)
4. **Set up backups** for PostgreSQL and data directories
5. **Monitor resources** (CPU, memory, disk)
6. **Use Docker secrets** for sensitive data
7. **Configure logging** to external service
8. **Set resource limits** in docker-compose.yml

## Next Steps

- See [Installation Guide](./installation.md) for non-Docker setup
- See [Quick Start Guide](./quick-start.md) for first-time usage
- See [Architecture Documentation](../architecture/) for system design


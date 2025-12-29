#!/bin/bash
# Mindscape AI Local Core - Start Script for Linux/macOS
# This script checks Docker availability and starts services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Mindscape AI Local Core - Start Script ==="
echo ""

# Function to check Docker availability
check_docker() {
    echo "Checking Docker availability..."

    # Check if docker command exists
    if ! command -v docker &> /dev/null; then
        echo "  ✗ Docker command not found"
        return 1
    fi
    echo "  ✓ Docker client found"

    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        echo "  ✗ Docker daemon is not running"
        return 1
    fi
    echo "  ✓ Docker daemon is running"

    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        echo "  ✗ Docker Compose not available"
        return 1
    fi
    COMPOSE_VERSION=$(docker compose version 2>&1)
    echo "  ✓ Docker Compose: $COMPOSE_VERSION"

    return 0
}

# Check Docker if not skipped
if [ "$1" != "--skip-check" ]; then
    if ! check_docker; then
        echo ""
        echo "❌ Docker is not available or not running"
        echo ""
        echo "Please ensure:"
        echo "  1. Docker is installed"
        echo "  2. Docker daemon is running"
        echo ""
        echo "To start Docker:"
        echo "  - Linux: sudo systemctl start docker"
        echo "  - macOS: Open Docker Desktop from Applications"
        echo ""
        echo "After starting Docker, run this script again:"
        echo "  ./scripts/start.sh"
        echo ""
        exit 1
    fi

    echo ""
    echo "✅ Docker is ready"
    echo ""
fi

# Change to project root
cd "$PROJECT_ROOT"

# Check for existing containers with same names and offer to clean them up
echo "Checking for existing containers..."
EXISTING_CONTAINERS=$(docker ps -a --filter "name=mindscape-ai-local-core" --format "{{.Names}}" 2>/dev/null)
if [ -n "$EXISTING_CONTAINERS" ]; then
    echo ""
    echo "⚠️  Found existing containers with conflicting names:"
    echo "$EXISTING_CONTAINERS" | while read -r container; do
        if [ -n "$container" ]; then
            echo "  - $container"
        fi
    done
    echo ""
    echo "These containers may prevent new containers from starting."
    echo ""
    read -p "Would you like to remove them? (Y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing containers..."
        docker compose down 2>/dev/null
        # Also try to remove individual containers if compose down didn't work
        echo "$EXISTING_CONTAINERS" | while read -r container; do
            if [ -n "$container" ]; then
                docker rm -f "$container" 2>/dev/null
            fi
        done
        echo "  ✓ Containers removed"
        echo ""
    else
        echo ""
        echo "⚠️  Keeping existing containers. If you encounter errors, run:"
        echo "  docker compose down"
        echo "  docker compose up -d"
        echo ""
    fi
fi

echo "Starting services..."
echo ""

# Start services
echo "Building and starting containers..."
docker compose up -d

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Failed to start services"
    echo ""
    
    # Wait a moment for containers to initialize
    sleep 2
    
    # Check which services failed
    echo "Checking service status..."
    FAILED_SERVICES=$(docker compose ps --format json 2>/dev/null | jq -r '.[] | select(.State != "running" and .State != "healthy") | .Service' 2>/dev/null || docker compose ps --format "{{.Service}}\t{{.State}}" | grep -v "running\|healthy" | cut -f1)
    
    if [ -n "$FAILED_SERVICES" ]; then
        echo ""
        echo "⚠️  The following services failed to start:"
        docker compose ps --format "table {{.Service}}\t{{.State}}" | grep -v "running\|healthy" || true
        echo ""
        
        # Show logs for failed services
        echo "Showing logs for failed services..."
        echo ""
        for service in $FAILED_SERVICES; do
            echo "=== Logs for $service ==="
            docker compose logs --tail=50 "$service" 2>/dev/null || docker compose logs --tail=50
            echo ""
        done
    else
        # If we can't parse, show all logs
        echo "Showing recent logs from all services..."
        echo ""
        docker compose logs --tail=50
    fi
    
    echo ""
    echo "For more detailed logs, run:"
    echo "  docker compose logs [service-name]"
    echo ""
    echo "To check service status:"
    echo "  docker compose ps"
    echo ""
    exit 1
fi

# Check if any services are unhealthy after starting
sleep 3
UNHEALTHY_SERVICES=$(docker compose ps --format json 2>/dev/null | jq -r '.[] | select(.Health == "unhealthy") | .Service' 2>/dev/null || docker compose ps --format "{{.Service}}\t{{.Health}}" | grep "unhealthy" | cut -f1)

if [ -n "$UNHEALTHY_SERVICES" ]; then
    echo ""
    echo "⚠️  Warning: Some services are unhealthy:"
    docker compose ps --format "table {{.Service}}\t{{.Health}}" | grep "unhealthy" || true
    echo ""
    echo "Showing logs for unhealthy services..."
    echo ""
    for service in $UNHEALTHY_SERVICES; do
        echo "=== Logs for $service ==="
        docker compose logs --tail=50 "$service" 2>/dev/null || docker compose logs --tail=50
        echo ""
    done
    echo ""
    echo "Services may still be starting. Check again with:"
    echo "  docker compose ps"
    echo "  docker compose logs [service-name]"
    echo ""
fi

echo ""
echo "✅ Services started successfully!"
echo ""
echo "Access the application:"
echo "  Frontend: http://localhost:8300"
echo "  Backend API: http://localhost:8200"
echo "  API Docs: http://localhost:8200/docs"
echo ""
echo "Useful commands:"
echo "  docker compose ps          # Check service status"
echo "  docker compose logs -f     # View logs"
echo "  docker compose stop        # Stop services"
echo "  docker compose down        # Stop and remove containers"
echo ""


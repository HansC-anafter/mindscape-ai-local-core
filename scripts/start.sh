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

echo "Starting services..."
echo ""

# Start services
docker compose up -d

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Failed to start services"
    echo ""
    echo "Check logs with:"
    echo "  docker compose logs"
    exit 1
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


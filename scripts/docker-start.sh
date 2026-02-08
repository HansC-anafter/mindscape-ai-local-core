#!/bin/bash

# Script to stop old repo Docker and start new repo Docker

set -e

echo "🛑 Stopping old repo Docker services..."
cd /Users/shock/Projects_local/workspace/my-agent-mindscape
docker compose down 2>/dev/null || echo "Old repo Docker already stopped or not running"

echo ""
echo "🚀 Starting new repo Docker services..."
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core

# Ensure PLAYBOOK_DISABLE_LEGACY is set in .env
if [ -f .env ]; then
    if ! grep -q "PLAYBOOK_DISABLE_LEGACY" .env; then
        echo "PLAYBOOK_DISABLE_LEGACY=1" >> .env
        echo "✅ Added PLAYBOOK_DISABLE_LEGACY=1 to .env"
    fi
else
    echo "PLAYBOOK_DISABLE_LEGACY=1" > .env
    echo "✅ Created .env with PLAYBOOK_DISABLE_LEGACY=1"
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cat > .env << 'ENVEOF'
# LLM Providers (at least one required)
# OPENAI_API_KEY=your_openai_api_key_here
# ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Database (PostgreSQL primary)
POSTGRES_CORE_DB=mindscape_core
POSTGRES_VECTOR_DB=mindscape_vectors
POSTGRES_CORE_USER=mindscape
POSTGRES_CORE_PASSWORD=mindscape_password
POSTGRES_VECTOR_USER=mindscape
POSTGRES_VECTOR_PASSWORD=mindscape_password
DATABASE_URL=postgresql://mindscape:mindscape_password@postgres:5432/mindscape_core
DATABASE_URL_CORE=postgresql://mindscape:mindscape_password@postgres:5432/mindscape_core
DATABASE_URL_VECTOR=postgresql://mindscape:mindscape_password@postgres:5432/mindscape_vectors

# Security
LOCAL_AUTH_SECRET=dev-secret-key-change-in-production

# Logging
LOG_LEVEL=INFO

# LLM Intent Extractor
ENABLE_LLM_INTENT_EXTRACTOR=true

# OCR Service
OCR_USE_GPU=false
OCR_LANG=ch

# Timezone
TZ=UTC
ENVEOF
    echo "✅ Created .env file. Please edit it and add your API keys before starting services."
    echo ""
fi

echo "📦 Building and starting Docker services..."
docker compose up -d --build

echo ""
echo "⏳ Waiting for services to start..."
sleep 5

echo ""
echo "📊 Service status:"
docker compose ps

echo ""
echo "📝 Recent logs:"
docker compose logs --tail=10

echo ""
echo "✅ Docker services started!"
echo ""
echo "🌐 Access the application:"
echo "   - Frontend: http://localhost:3000"
echo "   - Backend API: http://localhost:8000"
echo "   - API Docs: http://localhost:8000/docs"
echo "   - OCR Service: http://localhost:8001"
echo ""
echo "📋 Useful commands:"
echo "   - View logs: docker compose logs -f"
echo "   - Stop services: docker compose down"
echo "   - Restart: docker compose restart"

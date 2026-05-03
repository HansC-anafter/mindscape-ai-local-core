#!/bin/bash

# Mindscape AI Local Core - Setup Script
# This script helps initialize the project for local development
# Supports: macOS, Linux

set -e

echo "Mindscape AI Local Core - Setup"
echo "===================================="
echo ""

# Detect platform
PLATFORM="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macos"
fi

echo "Platform: $PLATFORM"
echo ""

# Check Python version
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo "   OK Found Python $PYTHON_VERSION"

    # Check version >= 3.9
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 9 ]); then
        echo "   WARNING  Python 3.9+ required. Found $PYTHON_VERSION"
        exit 1
    fi
else
    echo "   ERROR Python 3 not found. Please install Python 3.9+"
    exit 1
fi

# Check Node.js (optional)
echo "Checking Node.js (optional for frontend)..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo "   OK Found Node.js $NODE_VERSION"
else
    echo "   WARNING  Node.js not found. Frontend will not be available."
    echo "      Install Node.js 18+ if you want to use the web console."
fi

# Create data directory
echo "Creating data directory..."
mkdir -p data
echo "   OK Data directory created"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "   OK .env file created"
        echo "   WARNING  Please edit .env and add your API keys (OPENAI_API_KEY or ANTHROPIC_API_KEY)"
    else
        echo "   WARNING  .env.example not found. Creating basic .env..."
        cat > .env << EOF
# LLM Provider API Keys (at least one is required)
OPENAI_API_KEY=your-openai-api-key-here
# ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Application Settings
DEFAULT_LOCALE=en
EOF
        echo "   OK Basic .env file created"
    fi
else
    echo "   OK .env file already exists"
fi

# Install Python dependencies
echo "Installing Python dependencies..."
cd backend

if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
    echo "   OK Virtual environment created"
fi

echo "   Activating virtual environment..."
source venv/bin/activate

echo "   Upgrading pip..."
pip install --upgrade pip --quiet

echo "   Installing dependencies..."
pip install -r requirements.txt --quiet
echo "   OK Python dependencies installed"

cd ..

# Install frontend dependencies (if Node.js is available)
if command -v node &> /dev/null; then
    if [ -d "web-console" ]; then
        echo "Installing frontend dependencies..."
        cd web-console
        npm install --silent
        echo "   OK Frontend dependencies installed"
        cd ..
    else
        echo "   WARNING  web-console directory not found. Skipping frontend setup."
    fi

    # Install Device Node (for host-level operations)
    if [ -d "device-node" ]; then
        echo "Installing Device Node..."
        cd device-node
        npm install --silent
        npm run build --silent 2>/dev/null || echo "   WARNING  Build failed, will retry on first run"
        echo "   OK Device Node installed"
        cd ..
    fi
fi

# Initialize database
echo "Initializing database..."
cd backend
python -m app.init_db
echo "   OK Database initialized"
cd ..

echo ""
echo "OK Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env file and add your LLM API key"
echo "  2. Start backend: cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
if command -v node &> /dev/null && [ -d "web-console" ]; then
    echo "  3. Start frontend: cd web-console && npm run dev"
fi
echo ""
echo "For more information, see:"
echo "  - Installation Guide: docs/getting-started/installation.md"
echo "  - Quick Start: docs/getting-started/quick-start.md"
echo ""


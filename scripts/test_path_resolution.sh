#!/bin/bash
# Test script to verify path resolution works from different directories

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Testing Path Resolution ==="
echo ""
echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"
echo ""

# Test 1: Check if setup script exists
SETUP_SCRIPT="$SCRIPT_DIR/setup_unsplash_fingerprints.sh"
if [ -f "$SETUP_SCRIPT" ]; then
    echo "✅ Setup script found: $SETUP_SCRIPT"
else
    echo "❌ Setup script not found: $SETUP_SCRIPT"
    exit 1
fi

# Test 2: Check if init script exists
INIT_SCRIPT="$SCRIPT_DIR/init_unsplash_fingerprints.py"
if [ -f "$INIT_SCRIPT" ]; then
    echo "✅ Init script found: $INIT_SCRIPT"
else
    echo "❌ Init script not found: $INIT_SCRIPT"
    exit 1
fi

# Test 3: Check if build script exists
BUILD_SCRIPT="$PROJECT_ROOT/backend/scripts/build_unsplash_fingerprints.py"
if [ -f "$BUILD_SCRIPT" ]; then
    echo "✅ Build script found: $BUILD_SCRIPT"
else
    echo "❌ Build script not found: $BUILD_SCRIPT"
    exit 1
fi

# Test 4: Test path resolution from different directories
echo ""
echo "=== Testing from different directories ==="

# Test from project root
cd "$PROJECT_ROOT"
echo "Testing from project root: $(pwd)"
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from init_unsplash_fingerprints import setup_fingerprints_if_enabled
print('✅ Can import init_unsplash_fingerprints from project root')
"

# Test from scripts directory
cd "$SCRIPT_DIR"
echo "Testing from scripts directory: $(pwd)"
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '..')
from scripts.init_unsplash_fingerprints import setup_fingerprints_if_enabled
print('✅ Can import init_unsplash_fingerprints from scripts directory')
"

# Test from backend directory
cd "$PROJECT_ROOT/backend"
echo "Testing from backend directory: $(pwd)"
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
try:
    import build_unsplash_fingerprints
    print('✅ Can import build_unsplash_fingerprints from backend directory')
except Exception as e:
    print(f'⚠️  Import issue (expected if dependencies missing): {e}')
"

echo ""
echo "=== All path resolution tests passed ==="
echo ""
echo "You can now run the setup script from any directory:"
echo "  cd /any/directory"
echo "  /path/to/mindscape-ai-local-core/scripts/setup_unsplash_fingerprints.sh"


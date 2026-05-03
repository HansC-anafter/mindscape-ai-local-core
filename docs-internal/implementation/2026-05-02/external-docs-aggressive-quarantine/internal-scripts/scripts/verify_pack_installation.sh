#!/bin/bash
# Pack Installation Verification Script
# 驗證 packs 安裝到 local-core 的狀態

set -e

CONTROL_PLANE_HOST_PORT="${MINDSCAPE_CONTROL_PLANE_HOST_PORT:-8220}"
API_URL="${API_URL:-http://localhost:${CONTROL_PLANE_HOST_PORT}}"
BACKEND_DIR="${BACKEND_DIR:-backend}"
CURL_MAX_TIME="${CURL_MAX_TIME:-10}"

curl_json() {
    curl -sS --max-time "${CURL_MAX_TIME}" "$@"
}

echo "🔍 Pack Installation Verification"
echo "=================================="
echo ""

# 1. Check API health
echo "1. Checking API health..."
HEALTH=$(curl_json "${API_URL}/health" || echo "{}")
if echo "$HEALTH" | grep -q "healthy"; then
    echo "   ✅ API is healthy"
else
    echo "   ❌ API is not healthy"
    exit 1
fi
echo ""

# 2. List installed packs
echo "2. Listing installed packs..."
INSTALLED=$(curl_json "${API_URL}/api/v1/capability-packs/installed" || echo "[]")
INSTALLED_COUNT=$(echo "$INSTALLED" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data) if isinstance(data, list) else 0)")
echo "   📦 Installed packs: $INSTALLED_COUNT"
if [ "$INSTALLED_COUNT" -gt 0 ]; then
    echo "$INSTALLED" | python3 -m json.tool | head -30
fi
echo ""

# 3. List enabled packs
echo "3. Listing enabled packs..."
ENABLED=$(curl_json "${API_URL}/api/v1/capability-packs/enabled" || echo "[]")
ENABLED_COUNT=$(echo "$ENABLED" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data) if isinstance(data, list) else 0)")
echo "   ✅ Enabled packs: $ENABLED_COUNT"
if [ "$ENABLED_COUNT" -gt 0 ]; then
    echo "$ENABLED" | python3 -m json.tool | head -20
fi
echo ""

# 4. Check capabilities directory
echo "4. Checking capabilities directory..."
if [ -d "${BACKEND_DIR}/app/capabilities" ]; then
    CAP_COUNT=$(find "${BACKEND_DIR}/app/capabilities" -mindepth 1 -maxdepth 1 -type d | wc -l)
    echo "   📁 Capabilities found: $CAP_COUNT"
    echo "   Directories:"
    ls -1 "${BACKEND_DIR}/app/capabilities" | head -10 | sed 's/^/      - /'
else
    echo "   ⚠️  Capabilities directory not found"
fi
echo ""

# 5. Check playbook specs
echo "5. Checking playbook specs..."
if [ -d "${BACKEND_DIR}/playbooks/specs" ]; then
    SPEC_COUNT=$(find "${BACKEND_DIR}/playbooks/specs" -name "*.json" | wc -l)
    echo "   📋 Playbook specs: $SPEC_COUNT"
else
    echo "   ⚠️  Playbook specs directory not found"
fi
echo ""

# 6. Check installed capabilities details
echo "6. Checking installed capabilities details..."
INSTALLED_CAPS=$(curl_json "${API_URL}/api/v1/capability-packs/installed-capabilities" || echo "[]")
if echo "$INSTALLED_CAPS" | python3 -c "import sys, json; data=json.load(sys.stdin); exit(0 if isinstance(data, list) and len(data) > 0 else 1)" 2>/dev/null; then
    CAP_COUNT=$(echo "$INSTALLED_CAPS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data) if isinstance(data, list) else 0)")
    echo "   📦 Installed capabilities: $CAP_COUNT"
    echo "$INSTALLED_CAPS" | python3 -m json.tool | head -50
else
    echo "   ⚠️  Failed to get installed capabilities details"
fi
echo ""

echo "✅ Verification complete"
echo ""

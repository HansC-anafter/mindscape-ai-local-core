#!/bin/bash
# Install and Verify Packs Script
# 使用 installer 將 packs 安裝到 local-core 並驗證安裝

set -e

CONTROL_PLANE_HOST_PORT="${MINDSCAPE_CONTROL_PLANE_HOST_PORT:-8220}"
API_URL="${API_URL:-http://localhost:${CONTROL_PLANE_HOST_PORT}}"
PROVIDER_ID="${PROVIDER_ID:-mindscape-ai}"
CURL_MAX_TIME="${CURL_MAX_TIME:-10}"

curl_json() {
    curl -sS --max-time "${CURL_MAX_TIME}" "$@"
}

echo "🚀 Pack Installation and Verification"
echo "======================================"
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

# 2. List available packs from provider
echo "2. Listing available packs from provider '${PROVIDER_ID}'..."
PACKS_RESPONSE=$(curl_json "${API_URL}/api/v1/cloud-providers/${PROVIDER_ID}/packs" || echo "{}")
PACKS_COUNT=$(echo "$PACKS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict):
        packs = data.get('packs', [])
        print(len(packs) if isinstance(packs, list) else 0)
    else:
        print(0)
except:
    print(0)
" 2>/dev/null || echo "0")

if [ "$PACKS_COUNT" -gt 0 ]; then
    echo "   📦 Available packs: $PACKS_COUNT"
    echo "$PACKS_RESPONSE" | python3 -m json.tool | head -50
else
    echo "   ⚠️  No packs available or provider not configured"
    echo "$PACKS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PACKS_RESPONSE"
fi
echo ""

# 3. Install default packs
echo "3. Installing default packs from provider '${PROVIDER_ID}'..."
INSTALL_RESPONSE=$(curl_json -X POST "${API_URL}/api/v1/cloud-providers/${PROVIDER_ID}/install-default?bundle=default" || echo "{}")
INSTALL_SUCCESS=$(echo "$INSTALL_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict):
        success = data.get('success', False)
        installed = data.get('installed', [])
        errors = data.get('errors', [])
        print(f\"success={success}, installed={len(installed)}, errors={len(errors)}\")
    else:
        print('unknown')
except Exception as e:
    print(f'error: {e}')
" 2>/dev/null || echo "unknown")

echo "   Installation result: $INSTALL_SUCCESS"
echo "$INSTALL_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$INSTALL_RESPONSE"
echo ""

# 4. Wait for installation to complete
echo "4. Waiting for installation to complete..."
sleep 5
echo ""

# 5. Verify installed packs
echo "5. Verifying installed packs..."
INSTALLED=$(curl_json "${API_URL}/api/v1/capability-packs/installed" || echo "[]")
INSTALLED_COUNT=$(echo "$INSTALLED" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(len(data) if isinstance(data, list) else 0)
except:
    print(0)
" 2>/dev/null || echo "0")

echo "   📦 Installed packs: $INSTALLED_COUNT"
if [ "$INSTALLED_COUNT" -gt 0 ]; then
    echo "$INSTALLED" | python3 -m json.tool | head -30
fi
echo ""

# 6. Check installed capabilities details
echo "6. Checking installed capabilities details..."
INSTALLED_CAPS=$(curl_json "${API_URL}/api/v1/capability-packs/installed-capabilities" || echo "[]")
CAP_COUNT=$(echo "$INSTALLED_CAPS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(len(data) if isinstance(data, list) else 0)
except:
    print(0)
" 2>/dev/null || echo "0")

echo "   📦 Installed capabilities: $CAP_COUNT"
if [ "$CAP_COUNT" -gt 0 ]; then
    echo "$INSTALLED_CAPS" | python3 -m json.tool | head -80
fi
echo ""

echo "✅ Installation and verification complete"
echo ""

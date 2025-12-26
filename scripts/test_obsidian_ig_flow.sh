#!/bin/bash
# Test Obsidian -> IG Post -> IG Grid View Flow
# Workspace ID: bac7ce63-e768-454d-96f3-3a00e8e1df69

set -e

WORKSPACE_ID="bac7ce63-e768-454d-96f3-3a00e8e1df69"
API_BASE="http://localhost:8000/api/v1"
PLAYBOOK_CODE="ig_post_generation"

echo "=========================================="
echo "Testing Obsidian -> IG Post -> IG Grid View Flow"
echo "=========================================="
echo "Workspace ID: $WORKSPACE_ID"
echo ""

# Step 1: Check Obsidian configuration
echo "Step 1: Checking Obsidian configuration..."
OBSIDIAN_CONFIG=$(curl -s "$API_BASE/system-settings/obsidian" 2>/dev/null || echo "{}")
if [ "$OBSIDIAN_CONFIG" != "{}" ]; then
  echo "Obsidian Config:"
  echo "$OBSIDIAN_CONFIG" | python3 -m json.tool
else
  echo "⚠️  Obsidian config endpoint returned empty"
fi
echo ""

# Step 2: Check if ig_post_generation playbook is available
echo "Step 2: Checking ig_post_generation playbook..."
PLAYBOOK_INFO=$(curl -s "$API_BASE/playbooks/$PLAYBOOK_CODE")
echo "Playbook Info: $PLAYBOOK_INFO" | python3 -m json.tool | head -30
echo ""

# Step 3: Execute ig_post_generation playbook
echo "Step 3: Executing ig_post_generation playbook..."
echo "Note: This requires input content. Using sample input..."

EXECUTION_RESPONSE=$(curl -s -X POST "$API_BASE/playbooks/execute/start?playbook_code=$PLAYBOOK_CODE&workspace_id=$WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "content": "這是一個測試內容，用於生成 IG 貼文。",
      "target_language": "zh-TW"
    }
  }')

echo "Execution Response:"
echo "$EXECUTION_RESPONSE" | python3 -m json.tool

EXECUTION_ID=$(echo "$EXECUTION_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('execution_id', ''))")

if [ -z "$EXECUTION_ID" ]; then
  echo "❌ ERROR: Failed to get execution_id"
  exit 1
fi

echo ""
echo "Execution ID: $EXECUTION_ID"
echo ""

# Step 4: Check execution status
echo "Step 4: Checking execution status..."
sleep 3
STATUS_RESPONSE=$(curl -s "$API_BASE/playbooks/executions/$EXECUTION_ID?workspace_id=$WORKSPACE_ID")
echo "Status Response:"
echo "$STATUS_RESPONSE" | python3 -m json.tool | head -50
echo ""

# Step 5: Check artifacts (IG posts)
echo "Step 5: Checking artifacts (IG posts)..."
ARTIFACTS_RESPONSE=$(curl -s "$API_BASE/workspaces/$WORKSPACE_ID/artifacts?playbook_code=$PLAYBOOK_CODE")
echo "Artifacts Response:"
echo "$ARTIFACTS_RESPONSE" | python3 -m json.tool | head -100
echo ""

# Step 6: Check if IG Grid View API exists (should be in cloud)
echo "Step 6: Checking IG Grid View API..."
echo "Note: IG Grid View API should be in cloud repo, not local-core"
echo "Checking if cloud API is configured..."

CLOUD_API_URL=$(docker compose exec -T backend printenv CLOUD_API_URL 2>/dev/null || echo "")
if [ -n "$CLOUD_API_URL" ]; then
  echo "Cloud API URL: $CLOUD_API_URL"
  IG_POSTS_RESPONSE=$(curl -s "$CLOUD_API_URL/api/v1/workspaces/$WORKSPACE_ID/ig-posts" 2>/dev/null || echo "{\"error\": \"Cloud API not accessible\"}")
  echo "IG Posts Response:"
  echo "$IG_POSTS_RESPONSE" | python3 -m json.tool | head -50
else
  echo "⚠️  Cloud API URL not configured"
  echo "IG Grid View API should be accessed via cloud repo"
fi

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="


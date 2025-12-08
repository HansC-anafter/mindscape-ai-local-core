#!/bin/bash
# Test Three.js generation via Docker backend API
# This script tests the complete flow: start playbook -> continue conversation -> verify file generation

set -e

WORKSPACE_ID="931820cc-9bdc-4299-bb29-a439ea8f82a2"
PLAYBOOK_CODE="threejs_hero_landing"
PROFILE_ID="default-user"
API_BASE="http://localhost:8000"

echo "=== Starting Three.js Hero Landing Playbook Execution ==="
echo "Workspace ID: $WORKSPACE_ID"
echo "Playbook: $PLAYBOOK_CODE"
echo ""

# Step 1: Start playbook execution
echo "Step 1: Starting playbook execution..."
START_RESPONSE=$(curl -s -X POST "$API_BASE/api/v1/workspaces/$WORKSPACE_ID/playbooks/$PLAYBOOK_CODE/execute?profile_id=$PROFILE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "user_message": "生成一個動態粒子網絡的 Three.js hero 區塊，風格偏向科技感、未來主義。互動方式：滑鼠移動時產生視差效果，粒子會跟隨滑鼠移動。核心元素：標題文字「Mindscape AI」，副標題「智能代理工作台」，還有一個「開始使用」的 CTA 按鈕。請直接生成完整的程式碼。"
    }
  }')

EXECUTION_ID=$(echo "$START_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('execution_id', ''))" 2>/dev/null || echo "")

if [ -z "$EXECUTION_ID" ]; then
  echo "Error: Failed to get execution_id from start response"
  echo "Response: $START_RESPONSE"
  exit 1
fi

echo "Execution ID: $EXECUTION_ID"
echo ""

# Step 2: Continue conversation to generate code
echo "Step 2: Continuing conversation to generate code..."
sleep 2

CONTINUE_RESPONSE=$(curl -s -X POST "$API_BASE/api/v1/playbooks/execute/$EXECUTION_ID/continue?profile_id=$PROFILE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message": "請直接生成完整的 React Three Fiber 組件程式碼，包含所有必要的代碼和註釋。"
  }')

echo "Continue response received"
echo ""

# Step 3: Wait a bit and check for file generation
echo "Step 3: Checking for generated files..."
sleep 5

# Check workspace storage path
STORAGE_BASE="/app/data/workspaces/mindscape-ai-官網"
ARTIFACTS_DIR="artifacts"
EXECUTION_DIR="$STORAGE_BASE/$ARTIFACTS_DIR/$PLAYBOOK_CODE/$EXECUTION_ID"

echo "Expected execution directory (inside Docker): $EXECUTION_DIR"
echo ""

# Check if directory exists (from host machine)
HOST_STORAGE_BASE="./data/workspaces/mindscape-ai-官網"
HOST_EXECUTION_DIR="$HOST_STORAGE_BASE/$ARTIFACTS_DIR/$PLAYBOOK_CODE/$EXECUTION_ID"

if [ -d "$HOST_EXECUTION_DIR" ]; then
  echo "✓ Execution directory found: $HOST_EXECUTION_DIR"
  echo ""
  echo "Generated files:"
  ls -lah "$HOST_EXECUTION_DIR" || echo "Directory exists but cannot list contents"
  echo ""

  # Check for key files
  if [ -f "$HOST_EXECUTION_DIR/conversation_history.json" ]; then
    echo "✓ conversation_history.json found"
  fi

  if [ -f "$HOST_EXECUTION_DIR/execution_summary.md" ]; then
    echo "✓ execution_summary.md found"
  fi

  # Look for generated code files
  for file in "$HOST_EXECUTION_DIR"/*.{tsx,ts,js,html}; do
    if [ -f "$file" ]; then
      echo "✓ Generated code file: $(basename "$file")"
      echo "  Size: $(wc -c < "$file") bytes"
      echo "  First few lines:"
      head -5 "$file" | sed 's/^/    /'
      echo ""
    fi
  done
else
  echo "⚠ Execution directory not found yet: $HOST_EXECUTION_DIR"
  echo "  This might be normal if execution is still in progress"
  echo ""
  echo "Checking parent directories..."
  ls -lah "$HOST_STORAGE_BASE" 2>/dev/null || echo "Storage base directory not found"
  echo ""
fi

echo ""
echo "=== Test Summary ==="
echo "Execution ID: $EXECUTION_ID"
echo "Check files at: $HOST_EXECUTION_DIR"


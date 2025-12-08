#!/bin/bash

# Test script for Redis cache and tool call mechanism
# Tests the complete flow: Redis cache → Tool list → Tool calls → File generation

set -e

WORKSPACE_ID="931820cc-9bdc-4299-bb29-a439ea8f82a2"
PLAYBOOK_CODE="threejs_hero_landing"
API_BASE="http://localhost:8000/api/v1"

echo "=== Redis 緩存與工具調用機制測試 ==="
echo ""

# Step 1: Check Redis status
echo "步驟 1: 檢查 Redis 服務狀態..."
docker compose ps redis | grep -q "Up" && echo "✅ Redis 服務運行中" || echo "❌ Redis 服務未運行"
echo ""

# Step 2: Test Redis connection
echo "步驟 2: 測試 Redis 連接..."
docker compose exec -T redis redis-cli ping | grep -q "PONG" && echo "✅ Redis 連接正常" || echo "❌ Redis 連接失敗"
echo ""

# Step 3: Start Playbook execution
echo "步驟 3: 啟動 Playbook 執行..."
echo "工作區: $WORKSPACE_ID"
echo "Playbook: $PLAYBOOK_CODE"
echo ""

EXECUTION_RESPONSE=$(curl -s -X POST \
  "${API_BASE}/workspaces/${WORKSPACE_ID}/playbooks/${PLAYBOOK_CODE}/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "user_request": "生成一個 Three.js 英雄區塊，包含動畫效果和響應式設計"
    }
  }')

echo "執行響應:"
echo "$EXECUTION_RESPONSE" | jq '.' 2>/dev/null || echo "$EXECUTION_RESPONSE"
echo ""

# Extract execution_id
EXECUTION_ID=$(echo "$EXECUTION_RESPONSE" | jq -r '.execution_id' 2>/dev/null || echo "")

if [ -z "$EXECUTION_ID" ] || [ "$EXECUTION_ID" = "null" ]; then
  echo "❌ 無法獲取執行 ID，測試終止"
  exit 1
fi

echo "✅ 執行 ID: $EXECUTION_ID"
echo ""

# Step 4: Check backend logs for cache-related messages
echo "步驟 4: 檢查後端日誌（緩存相關）..."
echo "---"
docker compose logs backend --since 1m | grep -i -E "(cache|redis|tool.*list|preloaded)" | tail -10 || echo "（無相關日誌）"
echo "---"
echo ""

# Step 5: Continue execution (trigger tool calls)
echo "步驟 5: 繼續執行（觸發工具調用）..."
echo "等待 5 秒後繼續..."
sleep 5

CONTINUE_RESPONSE=$(curl -s -X POST \
  "${API_BASE}/playbooks/execute/${EXECUTION_ID}/continue" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message": "請使用 filesystem_write_file 工具將生成的 HTML 代碼寫入到 artifacts 目錄中"
  }')

echo "繼續執行響應:"
echo "$CONTINUE_RESPONSE" | jq '.' 2>/dev/null || echo "$CONTINUE_RESPONSE"
echo ""

# Step 6: Check backend logs for tool call parsing
echo "步驟 6: 檢查後端日誌（工具調用相關）..."
echo "---"
docker compose logs backend --since 1m | grep -i -E "(tool_call|parse|executing tool|write_file)" | tail -15 || echo "（無相關日誌）"
echo "---"
echo ""

# Step 7: Check Redis cache keys
echo "步驟 7: 檢查 Redis 緩存鍵..."
echo "---"
docker compose exec -T redis redis-cli KEYS "tool_registry:*" | head -10 || echo "（無緩存鍵）"
echo "---"
echo ""

# Step 8: Check generated files
echo "步驟 8: 檢查生成的文件..."
echo "---"
ARTIFACTS_DIR="./data/workspaces/${WORKSPACE_ID}/artifacts"
if [ -d "$ARTIFACTS_DIR" ]; then
  echo "✅ Artifacts 目錄存在"
  ls -lah "$ARTIFACTS_DIR" | head -10 || echo "（目錄為空）"
else
  echo "⚠️  Artifacts 目錄不存在: $ARTIFACTS_DIR"
fi
echo "---"
echo ""

echo "=== 測試完成 ==="
echo "執行 ID: $EXECUTION_ID"
echo "可以使用以下命令繼續執行："
echo "curl -X POST \"${API_BASE}/playbooks/execute/${EXECUTION_ID}/continue\" -H \"Content-Type: application/json\" -d '{\"user_message\": \"你的消息\"}'"


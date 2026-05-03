#!/bin/bash
# E2E 測試腳本 - Playbook Invocation Strategy
# 完整測試 standalone 和 plan_node 兩種模式

set -e

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Playbook Invocation Strategy E2E 測試${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 檢查服務
echo -e "${YELLOW}步驟 1: 檢查服務狀態...${NC}"
if ! curl -s "${BASE_URL}/health" > /dev/null; then
    echo -e "${RED}❌ 服務未運行，請先啟動: docker compose up -d${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 服務運行中${NC}"
echo ""

# 獲取可用 playbook
echo -e "${YELLOW}步驟 2: 獲取可用 Playbook...${NC}"
PLAYBOOK_CODE=$(curl -s "${BASE_URL}/api/v1/playbooks/" | jq -r '.[0].playbook_code' 2>/dev/null || echo "")
if [ -z "$PLAYBOOK_CODE" ]; then
    echo -e "${RED}❌ 無法獲取 playbook${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 使用 playbook: ${PLAYBOOK_CODE}${NC}"
echo ""

# 創建測試 workspace
echo -e "${YELLOW}步驟 3: 創建測試 Workspace...${NC}"
WORKSPACE_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/workspaces" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "E2E Test Workspace",
    "execution_mode": "execution"
  }')

WORKSPACE_ID=$(echo "$WORKSPACE_RESPONSE" | jq -r '.id' 2>/dev/null || echo "")
if [ -z "$WORKSPACE_ID" ] || [ "$WORKSPACE_ID" = "null" ]; then
    echo -e "${YELLOW}⚠️  無法創建 workspace，使用測試 ID: test-workspace${NC}"
    WORKSPACE_ID="test-workspace"
else
    echo -e "${GREEN}✅ Workspace 創建成功: ${WORKSPACE_ID}${NC}"
fi
echo ""

# 測試 Standalone Mode (Direct Path)
echo -e "${YELLOW}步驟 4: 測試 Standalone Mode (Direct Path)...${NC}"
echo -e "${BLUE}執行: POST /api/v1/playbooks/execute/start${NC}"

STANDALONE_RESPONSE=$(curl -s -X POST \
  "${BASE_URL}/api/v1/playbooks/execute/start?playbook_code=${PLAYBOOK_CODE}&profile_id=e2e-test-user&workspace_id=${WORKSPACE_ID}" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"query": "e2e test query"}}')

EXECUTION_ID=$(echo "$STANDALONE_RESPONSE" | jq -r '.execution_id // .id // empty' 2>/dev/null || echo "")

if [ -n "$EXECUTION_ID" ]; then
    echo -e "${GREEN}✅ Standalone 執行成功${NC}"
    echo -e "   Execution ID: ${EXECUTION_ID}"
    echo "$STANDALONE_RESPONSE" | jq '.' 2>/dev/null || echo "$STANDALONE_RESPONSE" | head -10
else
    echo -e "${YELLOW}⚠️  回應格式:${NC}"
    echo "$STANDALONE_RESPONSE" | head -10
fi
echo ""

# 檢查 Standalone 日誌
echo -e "${YELLOW}步驟 5: 檢查 Standalone Mode 日誌...${NC}"
echo -e "${BLUE}查看最近 30 條相關日誌:${NC}"
docker compose logs backend --tail 50 2>&1 | grep -i "standalone\|context_mode.*standalone\|invocation_mode.*standalone" | tail -5 || echo "未找到 standalone 相關日誌"
echo ""

# 等待一下讓執行完成
sleep 2

# 測試 Plan Node Mode (通過 Workspace Chat)
echo -e "${YELLOW}步驟 6: 測試 Plan Node Mode (Workspace Chat)...${NC}"
echo -e "${BLUE}執行: POST /api/v1/workspaces/{workspace_id}/chat (mode=execution)${NC}"

PLAN_RESPONSE=$(curl -s -X POST \
  "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "幫我分析數據",
    "mode": "execution",
    "stream": false
  }')

echo "$PLAN_RESPONSE" | jq '.' 2>/dev/null || echo "$PLAN_RESPONSE" | head -20
echo ""

# 檢查 Plan Node 日誌
echo -e "${YELLOW}步驟 7: 檢查 Plan Node Mode 日誌...${NC}"
echo -e "${BLUE}查看最近 30 條相關日誌:${NC}"
sleep 3
docker compose logs backend --tail 100 2>&1 | grep -i "plan_node\|plan_id\|task_id\|context_mode.*plan" | tail -10 || echo "未找到 plan_node 相關日誌"
echo ""

# 檢查策略路由日誌
echo -e "${YELLOW}步驟 8: 檢查策略路由日誌...${NC}"
echo -e "${BLUE}查看 PlaybookRunExecutor 日誌:${NC}"
docker compose logs backend --tail 200 2>&1 | grep -i "playbookrunexecutor.*context_mode\|handle_standalone\|handle_plan_node" | tail -10 || echo "未找到策略路由日誌"
echo ""

# 總結
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}E2E 測試完成${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "驗證檢查清單:"
echo "  [ ] Standalone 模式執行成功"
echo "  [ ] Plan Node 模式執行成功"
echo "  [ ] 日誌顯示正確的模式信息"
echo "  [ ] 兩種模式可以共存"
echo ""
echo "查看完整日誌:"
echo "  docker compose logs -f backend | grep -i 'standalone\\|plan_node\\|context_mode'"
echo ""



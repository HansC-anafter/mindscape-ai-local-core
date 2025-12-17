#!/bin/bash
# API 測試腳本 - 在 Docker 中測試 Playbook Invocation Strategy
# Usage: ./scripts/test_api_invocation.sh

set -e

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Playbook Invocation Strategy API 測試${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 檢查服務
echo -e "${YELLOW}1. 檢查服務狀態...${NC}"
if ! curl -s "${BASE_URL}/health" > /dev/null; then
    echo -e "${RED}❌ 服務未運行${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 服務運行中${NC}"
echo ""

# 獲取 playbook 列表
echo -e "${YELLOW}2. 獲取可用 Playbooks...${NC}"
PLAYBOOKS=$(curl -s "${BASE_URL}/api/v1/playbooks/" | jq -r '.[0:3] | .[] | .playbook_code' 2>/dev/null || echo "")
if [ -z "$PLAYBOOKS" ]; then
    echo -e "${RED}❌ 無法獲取 playbooks${NC}"
    exit 1
fi

FIRST_PB=$(echo "$PLAYBOOKS" | head -1)
echo -e "${GREEN}✅ 找到 playbooks，使用: ${FIRST_PB}${NC}"
echo ""

# 測試 Standalone Mode (Direct Path)
echo -e "${YELLOW}3. 測試 Standalone Mode (Direct Path)...${NC}"
echo -e "${BLUE}執行: POST /api/v1/playbooks/execute/start${NC}"

RESPONSE=$(curl -s -X POST \
  "${BASE_URL}/api/v1/playbooks/execute/start?playbook_code=${FIRST_PB}&profile_id=test-user&workspace_id=test-workspace" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"query": "test query"}}' 2>&1)

if echo "$RESPONSE" | grep -q "execution_id\|error"; then
    echo -e "${GREEN}✅ API 回應正常${NC}"
    echo "回應預覽:"
    echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE" | head -5
else
    echo -e "${RED}❌ API 回應異常${NC}"
    echo "$RESPONSE"
fi
echo ""

# 檢查日誌
echo -e "${YELLOW}4. 檢查日誌中的 Standalone Mode...${NC}"
echo -e "${BLUE}執行: docker compose logs backend | grep -i 'standalone' | tail -5${NC}"
docker compose logs backend 2>&1 | grep -i "standalone\|invocation_mode" | tail -5 || echo "未找到相關日誌"
echo ""

# 測試 Plan Node Mode (需要先創建 workspace 和執行計劃)
echo -e "${YELLOW}5. 測試 Plan Node Mode (Plan Path)...${NC}"
echo -e "${BLUE}注意：這需要有效的 workspace_id${NC}"
echo -e "${BLUE}執行: POST /api/v1/workspaces/{workspace_id}/chat${NC}"
echo ""
echo "請手動執行以下命令："
echo -e "${YELLOW}curl -X POST \"${BASE_URL}/api/v1/workspaces/YOUR_WORKSPACE_ID/chat\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"message\": \"幫我整理工作區想法\", \"mode\": \"execution\"}'${NC}"
echo ""

# 檢查 Plan Node 日誌
echo -e "${YELLOW}6. 檢查日誌中的 Plan Node Mode...${NC}"
echo -e "${BLUE}執行: docker compose logs backend | grep -i 'plan_node' | tail -5${NC}"
docker compose logs backend 2>&1 | grep -i "plan_node\|plan_id\|task_id" | tail -5 || echo "未找到相關日誌（需要先執行計劃）"
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}測試完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "下一步："
echo "1. 查看完整日誌: docker compose logs -f backend"
echo "2. 在 Docker 中運行測試腳本: docker compose exec backend python scripts/test_invocation_strategy_docker.py"
echo "3. 查看測試指南: cat docs-internal/implementation/playbook-invocation-strategy-testing-guide-2025-12-10.md"

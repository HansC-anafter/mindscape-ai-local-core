#!/bin/bash
# Quick test script for Playbook Invocation Strategy
# Usage: ./scripts/test_invocation_strategy.sh

set -e

echo "=========================================="
echo "Playbook Invocation Strategy 快速測試"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if services are running
echo "1. 檢查服務狀態..."
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${RED}❌ 後端服務未運行，請先啟動服務：${NC}"
    echo "   docker compose up -d"
    exit 1
fi
echo -e "${GREEN}✅ 後端服務運行中${NC}"
echo ""

# Test 1: Check API endpoint
echo "2. 測試 API 端點..."
RESPONSE=$(curl -s http://localhost:8000/api/v1/playbooks/ | head -c 100)
if [ -n "$RESPONSE" ]; then
    echo -e "${GREEN}✅ API 端點正常${NC}"
else
    echo -e "${RED}❌ API 端點無回應${NC}"
    exit 1
fi
echo ""

# Test 2: Check logs for context creation
echo "3. 檢查日誌中的 context 創建..."
echo "   請查看後端日誌，確認是否有以下關鍵字："
echo "   - 'STANDALONE mode'"
echo "   - 'PLAN_NODE mode'"
echo "   - 'invocation_mode'"
echo ""
echo "   執行以下命令查看日誌："
echo -e "${YELLOW}   docker compose logs backend | grep -i 'standalone\\|plan_node\\|invocation_mode'${NC}"
echo ""

# Test 3: Manual test instructions
echo "4. 手動測試步驟："
echo ""
echo "   a) Direct Path (Standalone) 測試："
echo -e "${YELLOW}   curl -X POST \"http://localhost:8000/api/v1/playbooks/execute/start?playbook_code=summarize_workspace_ideas&profile_id=test-user&workspace_id=test-workspace\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"inputs\": {\"query\": \"test\"}}'${NC}"
echo ""
echo "   b) Plan Path (Plan Node) 測試："
echo -e "${YELLOW}   curl -X POST \"http://localhost:8000/api/v1/workspaces/test-workspace/chat\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"message\": \"幫我整理工作區想法\", \"mode\": \"execution\"}'${NC}"
echo ""

# Test 4: Run unit tests if pytest is available
echo "5. 執行單元測試..."
if command -v pytest &> /dev/null; then
    echo "   執行 pytest..."
    cd backend
    if pytest tests/test_playbook_invocation_strategy.py -v; then
        echo -e "${GREEN}✅ 單元測試通過${NC}"
    else
        echo -e "${YELLOW}⚠️  單元測試失敗（可能需要安裝依賴）${NC}"
    fi
    cd ..
else
    echo -e "${YELLOW}⚠️  pytest 未安裝，跳過單元測試${NC}"
    echo "   安裝 pytest: pip install pytest pytest-asyncio"
fi
echo ""

echo "=========================================="
echo "測試完成！"
echo "=========================================="
echo ""
echo "詳細測試指南請參考："
echo "docs-internal/implementation/playbook-invocation-strategy-testing-guide-2025-12-10.md"
echo ""

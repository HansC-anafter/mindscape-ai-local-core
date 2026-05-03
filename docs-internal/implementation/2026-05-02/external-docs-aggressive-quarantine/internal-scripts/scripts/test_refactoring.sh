#!/bin/bash

# Playbook & Intent 重構快速測試腳本
# 用於快速驗證 P0-P2 功能是否正常工作

set -e

# 顏色定義
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 項目根目錄
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/web-console"

echo "=========================================="
echo "Playbook & Intent 重構測試腳本"
echo "=========================================="
echo ""

# 檢查後端服務是否運行
check_backend() {
    echo -e "${YELLOW}檢查後端服務...${NC}"
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 後端服務運行中 (http://localhost:8000)${NC}"
        return 0
    else
        echo -e "${RED}❌ 後端服務未運行${NC}"
        echo "請先啟動後端服務："
        echo "  cd $BACKEND_DIR"
        echo "  uvicorn app.main:app --reload"
        return 1
    fi
}

# 檢查前端服務是否運行
check_frontend() {
    echo -e "${YELLOW}檢查前端服務...${NC}"
    if curl -s http://localhost:3001 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 前端服務運行中 (http://localhost:3001)${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  前端服務未運行（可選）${NC}"
        echo "如需測試前端，請啟動前端服務："
        echo "  cd $FRONTEND_DIR"
        echo "  npm run dev"
        return 1
    fi
}

# 運行單元測試
run_unit_tests() {
    echo ""
    echo -e "${YELLOW}運行單元測試...${NC}"
    echo "----------------------------------------"
    cd "$PROJECT_ROOT"
    if python backend/test_playbook_refactoring.py; then
        echo -e "${GREEN}✅ 單元測試通過${NC}"
        return 0
    else
        echo -e "${RED}❌ 單元測試失敗${NC}"
        return 1
    fi
}

# 測試 PlaybookService API
test_playbook_service() {
    echo ""
    echo -e "${YELLOW}測試 PlaybookService API...${NC}"
    echo "----------------------------------------"

    # 測試查詢所有 playbooks
    echo "1. 測試查詢所有 playbooks..."
    response=$(curl -s http://localhost:8000/api/playbooks)
    if echo "$response" | grep -q "playbook_code"; then
        count=$(echo "$response" | grep -o "playbook_code" | wc -l | tr -d ' ')
        echo -e "${GREEN}   ✅ 找到 $count 個 playbooks${NC}"
    else
        echo -e "${RED}   ❌ 查詢失敗或返回格式錯誤${NC}"
        return 1
    fi

    # 測試分類篩選
    echo "2. 測試分類篩選..."
    response=$(curl -s "http://localhost:8000/api/playbooks?category=content")
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}   ✅ 分類篩選正常${NC}"
    else
        echo -e "${RED}   ❌ 分類篩選失敗${NC}"
        return 1
    fi

    echo -e "${GREEN}✅ PlaybookService API 測試通過${NC}"
    return 0
}

# 測試 API 文檔
test_api_docs() {
    echo ""
    echo -e "${YELLOW}測試 API 文檔...${NC}"
    echo "----------------------------------------"

    if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API 文檔可訪問 (http://localhost:8000/docs)${NC}"
        return 0
    else
        echo -e "${RED}❌ API 文檔無法訪問${NC}"
        return 1
    fi
}

# 主測試流程
main() {
    echo "開始測試..."
    echo ""

    # 檢查服務
    if ! check_backend; then
        exit 1
    fi

    check_frontend

    # 運行測試
    all_passed=true

    if ! run_unit_tests; then
        all_passed=false
    fi

    if ! test_api_docs; then
        all_passed=false
    fi

    if ! test_playbook_service; then
        all_passed=false
    fi

    # 總結
    echo ""
    echo "=========================================="
    if [ "$all_passed" = true ]; then
        echo -e "${GREEN}✅ 所有測試通過！${NC}"
        echo ""
        echo "下一步："
        echo "1. 打開前端 http://localhost:3001"
        echo "2. 測試 Agent Mode（Hybrid 模式）"
        echo "3. 測試 Execution Mode（直接 playbook.run）"
        echo ""
        echo "詳細測試指南："
        echo "  docs-internal/implementation/playbook-intent-refactoring-2025-12-04/testing-guide-2025-12-04.md"
    else
        echo -e "${RED}❌ 部分測試失敗，請檢查上述錯誤${NC}"
        exit 1
    fi
    echo "=========================================="
}

# 執行主流程
main


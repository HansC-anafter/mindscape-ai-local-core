#!/bin/bash

# Tool Registry API 驗證腳本
# 在 Docker 容器內執行

BASE_URL="${API_BASE_URL:-http://localhost:8000}"
PROFILE_ID="${PROFILE_ID:-default-user}"

echo "=== Tool Registry API 驗證 ==="
echo "Base URL: $BASE_URL"
echo "Profile ID: $PROFILE_ID"
echo ""

# 顏色輸出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

# 測試函數
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4

    echo -n "測試: $description ... "

    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL$endpoint" 2>/dev/null)
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    elif [ "$method" = "PATCH" ]; then
        response=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" 2>/dev/null)
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE_URL$endpoint" 2>/dev/null)
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "${GREEN}✓ 通過 (HTTP $http_code)${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ 失敗 (HTTP $http_code)${NC}"
        echo "  響應: $body" | head -3
        ((FAILED++))
        return 1
    fi
}

# 1. 連接管理 API
echo "=== 1. 連接管理 API ==="

# 1.1 創建連接
CONNECTION_DATA='{
    "tool_type": "local_filesystem",
    "connection_type": "local",
    "name": "Test Connection",
    "description": "Test connection for verification",
    "config": {"allowed_directories": ["/tmp"]}
}'
test_endpoint "POST" "/api/v1/tools/connections?profile_id=$PROFILE_ID" "$CONNECTION_DATA" "創建連接"

# 獲取 connection_id (從響應中提取)
CONNECTION_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/tools/connections?profile_id=$PROFILE_ID" \
    -H "Content-Type: application/json" \
    -d "$CONNECTION_DATA" 2>/dev/null)
CONNECTION_ID=$(echo "$CONNECTION_RESPONSE" | grep -o '"id":"[^"]*' | cut -d'"' -f4 | head -1)

if [ -z "$CONNECTION_ID" ]; then
    echo -e "${RED}無法獲取 connection_id，跳過後續測試${NC}"
    echo "響應: $CONNECTION_RESPONSE"
else
    echo "  創建的 Connection ID: $CONNECTION_ID"

    # 1.2 列出連接
    test_endpoint "GET" "/api/v1/tools/connections?profile_id=$PROFILE_ID" "" "列出連接"

    # 1.3 獲取單個連接
    test_endpoint "GET" "/api/v1/tools/connections/$CONNECTION_ID?profile_id=$PROFILE_ID" "" "獲取單個連接"

    # 1.4 更新連接
    UPDATE_DATA='{
        "description": "Updated description"
    }'
    test_endpoint "PATCH" "/api/v1/tools/connections/$CONNECTION_ID?profile_id=$PROFILE_ID" "$UPDATE_DATA" "更新連接"

    # 1.5 驗證連接
    VALIDATE_DATA='{
        "connection_id": "'$CONNECTION_ID'",
        "tool_type": "local_filesystem"
    }'
    test_endpoint "POST" "/api/v1/tools/connections/validate?profile_id=$PROFILE_ID" "$VALIDATE_DATA" "驗證連接"

    # 1.6 記錄使用
    test_endpoint "POST" "/api/v1/tools/connections/$CONNECTION_ID/record-usage?profile_id=$PROFILE_ID" "" "記錄使用"

    # 1.7 獲取統計信息
    test_endpoint "GET" "/api/v1/tools/connections/$CONNECTION_ID/statistics?profile_id=$PROFILE_ID" "" "獲取統計信息"

    # 1.8 刪除連接
    test_endpoint "DELETE" "/api/v1/tools/connections/$CONNECTION_ID?profile_id=$PROFILE_ID" "" "刪除連接"
fi

# 2. 工具狀態 API
echo ""
echo "=== 2. 工具狀態 API ==="

# 2.1 獲取所有工具狀態
test_endpoint "GET" "/api/v1/tools/status?profile_id=$PROFILE_ID" "" "獲取所有工具狀態"

# 2.2 獲取工具類型狀態
test_endpoint "GET" "/api/v1/tools/local_filesystem/status?profile_id=$PROFILE_ID" "" "獲取工具類型狀態"

# 2.3 獲取工具健康狀態
test_endpoint "GET" "/api/v1/tools/local_filesystem/health?profile_id=$PROFILE_ID" "" "獲取工具健康狀態"

# 3. 基礎工具 API
echo ""
echo "=== 3. 基礎工具 API ==="

# 3.1 獲取提供者列表
test_endpoint "GET" "/api/v1/tools/providers" "" "獲取提供者列表"

# 3.2 列出所有工具
test_endpoint "GET" "/api/v1/tools/" "" "列出所有工具"

# 4. 工具註冊 API
echo ""
echo "=== 4. 工具註冊 API ==="

# 4.1 註冊工具 (需要先創建連接)
CONNECTION_DATA2='{
    "tool_type": "local_filesystem",
    "connection_type": "local",
    "name": "Registration Test Connection",
    "config": {"allowed_directories": ["/tmp"]}
}'
CONNECTION_RESPONSE2=$(curl -s -X POST "$BASE_URL/api/v1/tools/connections?profile_id=$PROFILE_ID" \
    -H "Content-Type: application/json" \
    -d "$CONNECTION_DATA2" 2>/dev/null)
CONNECTION_ID2=$(echo "$CONNECTION_RESPONSE2" | grep -o '"id":"[^"]*' | cut -d'"' -f4 | head -1)

if [ -n "$CONNECTION_ID2" ]; then
    REGISTER_DATA='{
        "tool_id": "local_filesystem_read",
        "connection_id": "'$CONNECTION_ID2'",
        "profile_id": "'$PROFILE_ID'"
    }'
    test_endpoint "POST" "/api/v1/tools/register" "$REGISTER_DATA" "註冊工具"

    # 4.2 驗證工具
    test_endpoint "GET" "/api/v1/tools/verify/local_filesystem_read" "" "驗證工具"

    # 清理
    curl -s -X DELETE "$BASE_URL/api/v1/tools/connections/$CONNECTION_ID2?profile_id=$PROFILE_ID" > /dev/null
fi

# 5. 工具執行 API
echo ""
echo "=== 5. 工具執行 API ==="

# 5.1 執行歷史
test_endpoint "GET" "/api/v1/tools/execution-history?profile_id=$PROFILE_ID" "" "獲取執行歷史"

# 5.2 執行統計
test_endpoint "GET" "/api/v1/tools/execution-statistics?profile_id=$PROFILE_ID" "" "獲取執行統計"

echo ""
echo "=== 驗證完成 ==="
echo -e "${GREEN}通過: $PASSED${NC}"
echo -e "${RED}失敗: $FAILED${NC}"
echo "總計: $((PASSED + FAILED))"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}所有測試通過！${NC}"
    exit 0
else
    echo -e "${RED}有 $FAILED 個測試失敗${NC}"
    exit 1
fi


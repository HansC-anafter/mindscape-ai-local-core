#!/bin/bash
# Dashboard API Test Script
# Tests all Dashboard API endpoints and validates responses

BASE_URL="http://localhost:8200"
API_BASE="${BASE_URL}/api/v1/dashboard"

echo "=========================================="
echo "Dashboard API Test Suite"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local expected_status=$4
    local description=$5

    echo -n "Testing: $description ... "

    if [ -z "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" "${API_BASE}${endpoint}" \
            -H "Content-Type: application/json")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "${API_BASE}${endpoint}" \
            -H "Content-Type: application/json" \
            -d "$data")
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" -eq "$expected_status" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP $http_code)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}FAIL${NC} (Expected HTTP $expected_status, got $http_code)"
        echo "Response: $body"
        ((FAILED++))
        return 1
    fi
}

# Test 1: GET /summary (global scope)
test_endpoint "GET" "/summary?scope=global" "" 200 "GET Summary (global scope)"

# Test 2: POST /summary
test_endpoint "POST" "/summary" '{"scope":"global","view":"my_work"}' 200 "POST Summary"

# Test 3: GET /inbox
test_endpoint "GET" "/inbox?scope=global&limit=10" "" 200 "GET Inbox"

# Test 4: POST /inbox
test_endpoint "POST" "/inbox" '{"scope":"global","limit":10}' 200 "POST Inbox"

# Test 5: GET /cases
test_endpoint "GET" "/cases?scope=global&limit=10" "" 200 "GET Cases"

# Test 6: GET /assignments
test_endpoint "GET" "/assignments?scope=global&limit=10" "" 200 "GET Assignments"

# Test 7: GET /saved-views
test_endpoint "GET" "/saved-views" "" 200 "GET Saved Views"

# Test 8: POST /saved-views (create)
test_endpoint "POST" "/saved-views" '{"name":"Test View","scope":"global","view":"my_work","tab":"inbox"}' 201 "POST Create Saved View"

# Test 9: Invalid scope format (should fallback to global)
test_endpoint "GET" "/summary?scope=invalid:format" "" 200 "Invalid scope format (fallback)"

# Test 10: Workspace scope (if user has workspaces)
test_endpoint "GET" "/summary?scope=workspace:test-workspace-id" "" 200 "Workspace scope"

echo ""
echo "=========================================="
echo "Test Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo "=========================================="

if [ $FAILED -eq 0 ]; then
    exit 0
else
    exit 1
fi

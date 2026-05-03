#!/usr/bin/env python3
"""
Tool Registry API 驗證腳本
在 Docker 容器內執行
"""

import os
import sys
import json
import requests
from typing import Dict, Any, Optional
from datetime import datetime

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PROFILE_ID = os.getenv("PROFILE_ID", "default-user")

# 顏色輸出
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'  # No Color

PASSED = 0
FAILED = 0
RESULTS = []

def test_endpoint(method: str, endpoint: str, data: Optional[Dict] = None, description: str = "") -> bool:
    """測試 API 端點"""
    global PASSED, FAILED

    url = f"{BASE_URL}{endpoint}"
    print(f"測試: {description} ... ", end="", flush=True)

    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        elif method == "PATCH":
            response = requests.patch(url, json=data, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, timeout=10)
        else:
            print(f"{Colors.RED}✗ 失敗 (無效的方法){Colors.NC}")
            FAILED += 1
            return False

        if 200 <= response.status_code < 300:
            print(f"{Colors.GREEN}✓ 通過 (HTTP {response.status_code}){Colors.NC}")
            PASSED += 1
            RESULTS.append({
                "endpoint": endpoint,
                "method": method,
                "status": "PASS",
                "status_code": response.status_code,
                "description": description
            })
            return True
        else:
            print(f"{Colors.RED}✗ 失敗 (HTTP {response.status_code}){Colors.NC}")
            try:
                error_msg = response.json()
                print(f"  錯誤: {str(error_msg)[:100]}")
            except:
                print(f"  響應: {response.text[:100]}")
            FAILED += 1
            RESULTS.append({
                "endpoint": endpoint,
                "method": method,
                "status": "FAIL",
                "status_code": response.status_code,
                "description": description,
                "error": response.text[:200]
            })
            return False
    except requests.exceptions.RequestException as e:
        print(f"{Colors.RED}✗ 失敗 (連接錯誤: {str(e)[:50]}){Colors.NC}")
        FAILED += 1
        RESULTS.append({
            "endpoint": endpoint,
            "method": method,
            "status": "ERROR",
            "description": description,
            "error": str(e)
        })
        return False

def main():
    global PASSED, FAILED

    print("=== Tool Registry API 驗證 ===")
    print(f"Base URL: {BASE_URL}")
    print(f"Profile ID: {PROFILE_ID}")
    print()

    # 1. 連接管理 API
    print("=== 1. 連接管理 API ===")

    # 1.1 創建連接
    connection_data = {
        "tool_type": "local_filesystem",
        "connection_type": "local",
        "name": "Test Connection",
        "description": "Test connection for verification",
        "config": {"allowed_directories": ["/tmp"]}
    }
    test_endpoint("POST", f"/api/v1/tools/connections?profile_id={PROFILE_ID}",
                  connection_data, "創建連接")

    # 獲取 connection_id
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/tools/connections?profile_id={PROFILE_ID}",
            json=connection_data,
            timeout=10
        )
        if response.status_code == 200:
            connection_id = response.json().get("id")
            print(f"  創建的 Connection ID: {connection_id}")
        else:
            connection_id = None
            print(f"  {Colors.RED}無法創建連接，跳過後續測試{Colors.NC}")
    except Exception as e:
        connection_id = None
        print(f"  {Colors.RED}無法創建連接: {e}{Colors.NC}")

    if connection_id:
        # 1.2 列出連接
        test_endpoint("GET", f"/api/v1/tools/connections?profile_id={PROFILE_ID}",
                      None, "列出連接")

        # 1.3 獲取單個連接
        test_endpoint("GET", f"/api/v1/tools/connections/{connection_id}?profile_id={PROFILE_ID}",
                      None, "獲取單個連接")

        # 1.4 更新連接
        update_data = {"description": "Updated description"}
        test_endpoint("PATCH", f"/api/v1/tools/connections/{connection_id}?profile_id={PROFILE_ID}",
                      update_data, "更新連接")

        # 1.5 驗證連接
        validate_data = {
            "connection_id": connection_id,
            "tool_type": "local_filesystem"
        }
        test_endpoint("POST", f"/api/v1/tools/connections/validate?profile_id={PROFILE_ID}",
                      validate_data, "驗證連接")

        # 1.6 記錄使用
        test_endpoint("POST", f"/api/v1/tools/connections/{connection_id}/record-usage?profile_id={PROFILE_ID}",
                      None, "記錄使用")

        # 1.7 獲取統計信息
        test_endpoint("GET", f"/api/v1/tools/connections/{connection_id}/statistics?profile_id={PROFILE_ID}",
                      None, "獲取統計信息")

        # 1.8 刪除連接
        test_endpoint("DELETE", f"/api/v1/tools/connections/{connection_id}?profile_id={PROFILE_ID}",
                      None, "刪除連接")

    # 2. 工具狀態 API
    print()
    print("=== 2. 工具狀態 API ===")

    # 2.1 獲取所有工具狀態
    test_endpoint("GET", f"/api/v1/tools/status?profile_id={PROFILE_ID}",
                  None, "獲取所有工具狀態")

    # 2.2 獲取工具類型狀態
    test_endpoint("GET", f"/api/v1/tools/local_filesystem/status?profile_id={PROFILE_ID}",
                  None, "獲取工具類型狀態")

    # 2.3 獲取工具健康狀態
    test_endpoint("GET", f"/api/v1/tools/local_filesystem/health?profile_id={PROFILE_ID}",
                  None, "獲取工具健康狀態")

    # 3. 基礎工具 API
    print()
    print("=== 3. 基礎工具 API ===")

    # 3.1 獲取提供者列表
    test_endpoint("GET", "/api/v1/tools/providers", None, "獲取提供者列表")

    # 3.2 列出所有工具
    test_endpoint("GET", "/api/v1/tools/", None, "列出所有工具")

    # 4. 工具註冊 API
    print()
    print("=== 4. 工具註冊 API ===")

    # 4.1 註冊工具 (需要先創建連接)
    try:
        connection_data2 = {
            "tool_type": "local_filesystem",
            "connection_type": "local",
            "name": "Registration Test Connection",
            "config": {"allowed_directories": ["/tmp"]}
        }
        response2 = requests.post(
            f"{BASE_URL}/api/v1/tools/connections?profile_id={PROFILE_ID}",
            json=connection_data2,
            timeout=10
        )
        if response2.status_code == 200:
            connection_id2 = response2.json().get("id")
            register_data = {
                "tool_id": "local_filesystem_read",
                "connection_id": connection_id2,
                "profile_id": PROFILE_ID
            }
            test_endpoint("POST", "/api/v1/tools/register", register_data, "註冊工具")

            # 4.2 驗證工具
            test_endpoint("GET", "/api/v1/tools/verify/local_filesystem_read",
                          None, "驗證工具")

            # 清理
            requests.delete(f"{BASE_URL}/api/v1/tools/connections/{connection_id2}?profile_id={PROFILE_ID}", timeout=10)
    except Exception as e:
        print(f"  {Colors.YELLOW}跳過註冊測試: {e}{Colors.NC}")

    # 5. 工具執行 API
    print()
    print("=== 5. 工具執行 API ===")

    # 5.1 執行歷史
    test_endpoint("GET", f"/api/v1/tools/execution-history?profile_id={PROFILE_ID}",
                  None, "獲取執行歷史")

    # 5.2 執行統計
    test_endpoint("GET", f"/api/v1/tools/execution-statistics?profile_id={PROFILE_ID}",
                  None, "獲取執行統計")

    # 輸出結果
    print()
    print("=== 驗證完成 ===")
    print(f"{Colors.GREEN}通過: {PASSED}{Colors.NC}")
    print(f"{Colors.RED}失敗: {FAILED}{Colors.NC}")
    print(f"總計: {PASSED + FAILED}")

    # 保存結果到文件
    result_file = f"/tmp/verification_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "base_url": BASE_URL,
            "profile_id": PROFILE_ID,
            "passed": PASSED,
            "failed": FAILED,
            "total": PASSED + FAILED,
            "results": RESULTS
        }, f, indent=2, ensure_ascii=False)
    print(f"結果已保存到: {result_file}")

    if FAILED == 0:
        print(f"{Colors.GREEN}所有測試通過！{Colors.NC}")
        return 0
    else:
        print(f"{Colors.RED}有 {FAILED} 個測試失敗{Colors.NC}")
        return 1

if __name__ == "__main__":
    sys.exit(main())


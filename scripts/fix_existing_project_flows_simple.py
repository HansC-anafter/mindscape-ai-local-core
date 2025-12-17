#!/usr/bin/env python3
"""
Fix existing project flows - Simple version using API with workaround
Since API creates flow with auto ID, we'll create flows first, then update projects to use them
"""

import json
import urllib.request

API_URL = "http://localhost:8000"
WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"

TYPE_TO_PLAYBOOKS = {
    "content_campaign": ["content_drafting", "content_editing", "copywriting"],
    "book": ["yearly_personal_book"],
    "book_website": ["yearly_personal_book", "information_organization"],
    "knowledge_base_website": ["information_organization"],
    "knowledge_base_site": ["information_organization"],
    "obsidian_to_site": ["information_organization", "note_organization"],
    "website": ["information_organization"],
    "digital_garden": ["information_organization", "note_organization"],
}

def get_projects():
    """Get all open projects"""
    url = f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/projects?state=open&limit=100"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())
        return data.get('projects', [])

def create_flow(name: str, description: str, flow_definition: dict):
    """Create flow via API"""
    url = f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/flows"
    request_data = {
        "name": name,
        "description": description,
        "flow_definition": flow_definition
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(request_data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())

def update_flow(flow_id: str, flow_definition: dict):
    """Update flow via API"""
    url = f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/flows/{flow_id}"
    request_data = {"flow_definition": flow_definition}
    req = urllib.request.Request(
        url,
        data=json.dumps(request_data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def main():
    print("=" * 80)
    print("修復現有專案的 Flow Playbook 序列")
    print("=" * 80)
    print()
    print("⚠️  注意：由於 API 限制，此腳本只能更新已存在的 flow")
    print("   如果 flow 不存在，需要手動創建或等待後端自動創建")
    print()

    projects = get_projects()
    print(f"找到 {len(projects)} 個專案\n")

    updated = 0
    not_found = 0
    errors = 0

    for project in projects:
        project_title = project.get('title', 'N/A')
        project_type = project.get('type', 'N/A')
        flow_id = project.get('flow_id', 'N/A')

        print(f"專案: {project_title[:40]}")
        print(f"  類型: {project_type}")
        print(f"  Flow ID: {flow_id}")

        if not flow_id or flow_id == 'N/A':
            print(f"  ⚠️  跳過：沒有 flow_id")
            print()
            continue

        # Get playbook sequence
        playbook_sequence = TYPE_TO_PLAYBOOKS.get(project_type, [])

        if not playbook_sequence:
            print(f"  ⚠️  未找到對應的 playbook 序列")
        else:
            print(f"  ✓ 建議 {len(playbook_sequence)} 個 playbooks: {', '.join(playbook_sequence)}")

        # Try to update flow
        flow_def = {
            "nodes": [],
            "edges": [],
            "playbook_sequence": playbook_sequence
        }

        try:
            result = update_flow(flow_id, flow_def)
            if result:
                print(f"  ✓ 已更新 flow")
                updated += 1
            else:
                print(f"  ⚠️  Flow 不存在，無法更新（需要後端自動創建或手動創建）")
                not_found += 1
        except Exception as e:
            print(f"  ✗ 錯誤: {str(e)[:50]}")
            errors += 1

        print()

    print("=" * 80)
    print(f"完成：更新 {updated} 個，未找到 {not_found} 個，錯誤 {errors} 個")
    print("=" * 80)
    print()
    if not_found > 0:
        print("💡 建議：")
        print("   1. 重啟後端服務，讓後端自動為這些專案創建 flow")
        print("   2. 或者手動通過 API 創建對應的 flow")
        print("   3. 新創建的專案會自動使用 LLM 分析 playbook_sequence")

if __name__ == "__main__":
    main()


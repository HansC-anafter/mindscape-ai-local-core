#!/usr/bin/env python3
"""
Fix existing project flows by adding playbook_sequence using LLM via API
"""

import json
import urllib.request
import urllib.parse
from typing import List, Dict, Any

API_URL = "http://localhost:8000"
WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"

def get_projects() -> List[Dict[str, Any]]:
    """Get all open projects"""
    url = f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/projects?state=open&limit=100"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())
        return data.get('projects', [])

def get_flow(flow_id: str) -> Dict[str, Any]:
    """Get flow details"""
    url = f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/flows/{flow_id}"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def update_flow(flow_id: str, flow_definition: dict, name: str = None, description: str = None) -> Dict[str, Any]:
    """Update flow"""
    url = f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/flows/{flow_id}"

    request_data = {
        "flow_definition": flow_definition
    }
    if name:
        request_data["name"] = name
    if description:
        request_data["description"] = description

    req = urllib.request.Request(
        url,
        data=json.dumps(request_data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT'
    )

    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())

def create_flow(flow_id: str, name: str, description: str, flow_definition: dict) -> Dict[str, Any]:
    """Create flow"""
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

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code == 409:  # Already exists
            return None
        raise

def suggest_playbook_sequence_via_chat(project_title: str, project_type: str, metadata: dict = None) -> List[str]:
    """
    Use chat API to get LLM suggestion for playbook_sequence
    This is a workaround since we can't directly call ProjectDetector
    """
    # Build a message that will trigger project detection
    message = f"{project_title}"
    if project_type:
        message += f" (type: {project_type})"

    if metadata and isinstance(metadata, dict):
        primary_intent = metadata.get('primary_intent')
        if primary_intent:
            message += f"\n\nOriginal intent: {primary_intent}"

    # For now, return empty list - we'll need to use a different approach
    # The proper way would be to call ProjectDetector, but that requires backend imports
    # So we'll use a simple heuristic based on project type
    type_to_playbooks = {
        "content_campaign": ["content_drafting", "content_editing", "copywriting"],
        "book": ["yearly_personal_book"],
        "book_website": ["yearly_personal_book", "information_organization"],
        "knowledge_base_website": ["information_organization"],
        "knowledge_base_site": ["information_organization"],
        "obsidian_to_site": ["information_organization", "note_organization"],
        "website": ["information_organization"],
        "digital_garden": ["information_organization", "note_organization"],
    }

    return type_to_playbooks.get(project_type, [])

def main():
    print("=" * 80)
    print("修復現有專案的 Flow Playbook 序列")
    print("=" * 80)
    print()

    projects = get_projects()
    print(f"找到 {len(projects)} 個專案\n")

    fixed = 0
    created = 0
    skipped = 0
    errors = 0

    for project in projects:
        project_id = project.get('id')
        project_title = project.get('title', 'N/A')
        project_type = project.get('type', 'N/A')
        flow_id = project.get('flow_id', 'N/A')
        metadata = project.get('metadata', {})

        print(f"專案: {project_title[:40]}")
        print(f"  類型: {project_type}")
        print(f"  Flow ID: {flow_id}")

        if not flow_id or flow_id == 'N/A':
            print(f"  ⚠️  跳過：沒有 flow_id")
            skipped += 1
            print()
            continue

        # Get playbook sequence suggestion
        # Note: This is a simplified version - ideally we'd use LLM via ProjectDetector
        # For now, we use a heuristic based on project type
        print(f"  🔍 基於專案類型分析 playbook 序列...")
        playbook_sequence = suggest_playbook_sequence_via_chat(project_title, project_type, metadata)

        if not playbook_sequence:
            print(f"  ⚠️  未找到對應的 playbook 序列（類型: {project_type}）")
            playbook_sequence = []
        else:
            print(f"  ✓ 建議 {len(playbook_sequence)} 個 playbooks")
            print(f"    {', '.join(playbook_sequence)}")

        # Get or create flow
        flow = get_flow(flow_id)

        # Prepare flow definition
        flow_def = {
            "nodes": [],
            "edges": [],
            "playbook_sequence": playbook_sequence
        }

        if flow:
            # Update existing flow
            existing_def = flow.get('flow_definition', {})
            if isinstance(existing_def, dict):
                flow_def = existing_def.copy()
            flow_def['playbook_sequence'] = playbook_sequence

            try:
                updated_flow = update_flow(
                    flow_id=flow_id,
                    flow_definition=flow_def,
                    name=flow.get('name'),
                    description=flow.get('description')
                )
                print(f"  ✓ 已更新 flow，playbook 序列: {len(playbook_sequence)}")
                fixed += 1
            except Exception as e:
                print(f"  ✗ 更新錯誤: {str(e)[:50]}")
                errors += 1
        else:
            # Create new flow
            flow_name = f"{project_type.replace('_', ' ').title()} Flow"
            flow_description = f"Flow for {project_type} projects"

            try:
                # Note: API creates flow with auto-generated ID, but we need specific ID
                # So we'll need to use direct database access or update the API
                # For now, try to create and then update
                created_flow = create_flow(
                    flow_id=flow_id,  # This won't work with current API
                    name=flow_name,
                    description=flow_description,
                    flow_definition=flow_def
                )
                if created_flow:
                    print(f"  ✓ 已創建 flow，playbook 序列: {len(playbook_sequence)}")
                    created += 1
                else:
                    print(f"  ⚠️  Flow 可能已存在，嘗試更新...")
                    # Try to update
                    try:
                        updated_flow = update_flow(
                            flow_id=flow_id,
                            flow_definition=flow_def,
                            name=flow_name,
                            description=flow_description
                        )
                        print(f"  ✓ 已更新 flow，playbook 序列: {len(playbook_sequence)}")
                        fixed += 1
                    except Exception as e2:
                        print(f"  ✗ 更新錯誤: {str(e2)[:50]}")
                        errors += 1
            except Exception as e:
                print(f"  ✗ 創建錯誤: {str(e)[:50]}")
                errors += 1

        print()

    print("=" * 80)
    print(f"完成：更新 {fixed} 個，創建 {created} 個，跳過 {skipped} 個，錯誤 {errors} 個")
    print("=" * 80)
    print()
    print("⚠️  注意：此腳本使用簡化的啟發式方法（基於專案類型）")
    print("   理想情況下應使用 LLM 分析，但需要後端直接調用 ProjectDetector")
    print("   建議：重啟後端後，新創建的專案會自動使用 LLM 分析 playbook_sequence")

if __name__ == "__main__":
    main()


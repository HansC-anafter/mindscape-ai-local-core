#!/usr/bin/env python3
"""
Fix existing project flows by adding playbook_sequence using direct database access
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Database path
WORKSPACE_ROOT = Path(__file__).parent.parent
DB_PATH = WORKSPACE_ROOT / "backend" / "data" / "mindscape.db"
if not DB_PATH.exists():
    DB_PATH = WORKSPACE_ROOT / "data" / "mindscape.db"

WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"

# Playbook mapping based on project type (heuristic approach)
# In production, this should be done by LLM via ProjectDetector
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

def get_projects(conn):
    """Get all open projects"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, type, title, flow_id, metadata
        FROM projects
        WHERE home_workspace_id = ? AND state = 'open'
        ORDER BY updated_at DESC
        LIMIT 100
    ''', (WORKSPACE_ID,))

    projects = []
    for row in cursor.fetchall():
        projects.append({
            'id': row[0],
            'type': row[1],
            'title': row[2],
            'flow_id': row[3],
            'metadata': json.loads(row[4]) if row[4] else {}
        })
    return projects

def get_flow(conn, flow_id: str):
    """Get flow from database"""
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM playbook_flows WHERE id = ?', (flow_id,))
    row = cursor.fetchone()
    if not row:
        return None

    columns = [desc[0] for desc in cursor.description]
    flow = dict(zip(columns, row))

    # Parse flow_definition JSON
    if flow.get('flow_definition'):
        flow['flow_definition'] = json.loads(flow['flow_definition'])
    else:
        flow['flow_definition'] = {}

    return flow

def create_flow(conn, flow_id: str, name: str, description: str, flow_definition: dict):
    """Create flow in database"""
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    cursor.execute('''
        INSERT INTO playbook_flows (id, name, description, flow_definition, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        flow_id,
        name,
        description,
        json.dumps(flow_definition),
        now,
        now
    ))
    conn.commit()
    return True

def update_flow(conn, flow_id: str, flow_definition: dict, name: str = None, description: str = None):
    """Update flow in database"""
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    updates = ['flow_definition = ?', 'updated_at = ?']
    params = [json.dumps(flow_definition), now]

    if name:
        updates.append('name = ?')
        params.append(name)
    if description:
        updates.append('description = ?')
        params.append(description)

    params.append(flow_id)

    cursor.execute(f'''
        UPDATE playbook_flows
        SET {', '.join(updates)}
        WHERE id = ?
    ''', params)
    conn.commit()
    return cursor.rowcount > 0

def main():
    if not DB_PATH.exists():
        print(f"❌ 數據庫文件不存在: {DB_PATH}")
        return

    print("=" * 80)
    print("修復現有專案的 Flow Playbook 序列")
    print("=" * 80)
    print(f"數據庫: {DB_PATH}")
    print()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        projects = get_projects(conn)
        print(f"找到 {len(projects)} 個專案\n")

        fixed = 0
        created = 0
        skipped = 0
        errors = 0

        for project in projects:
            project_id = project['id']
            project_title = project['title']
            project_type = project['type']
            flow_id = project['flow_id']
            metadata = project.get('metadata', {})

            print(f"專案: {project_title[:40]}")
            print(f"  類型: {project_type}")
            print(f"  Flow ID: {flow_id}")

            if not flow_id:
                print(f"  ⚠️  跳過：沒有 flow_id")
                skipped += 1
                print()
                continue

            # Get playbook sequence based on project type
            playbook_sequence = TYPE_TO_PLAYBOOKS.get(project_type, [])

            if not playbook_sequence:
                print(f"  ⚠️  未找到對應的 playbook 序列（類型: {project_type}）")
            else:
                print(f"  ✓ 建議 {len(playbook_sequence)} 個 playbooks")
                print(f"    {', '.join(playbook_sequence)}")

            # Get or create flow
            flow = get_flow(conn, flow_id)

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
                    update_flow(
                        conn,
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
                    create_flow(
                        conn,
                        flow_id=flow_id,
                        name=flow_name,
                        description=flow_description,
                        flow_definition=flow_def
                    )
                    print(f"  ✓ 已創建 flow，playbook 序列: {len(playbook_sequence)}")
                    created += 1
                except Exception as e:
                    print(f"  ✗ 創建錯誤: {str(e)[:50]}")
                    errors += 1

            print()

        print("=" * 80)
        print(f"完成：更新 {fixed} 個，創建 {created} 個，跳過 {skipped} 個，錯誤 {errors} 個")
        print("=" * 80)
        print()
        print("⚠️  注意：此腳本使用簡化的啟發式方法（基於專案類型）")
        print("   理想情況下應使用 LLM 分析，但需要後端環境設置")
        print("   建議：重啟後端後，新創建的專案會自動使用 LLM 分析 playbook_sequence")

    finally:
        conn.close()

if __name__ == "__main__":
    main()


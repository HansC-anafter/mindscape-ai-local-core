#!/usr/bin/env python3
"""
Investigation script for Aura CIS welcome message issue

Checks database for any data containing "Aura CIS" or "武林逸亭" that might
be causing the welcome message to include these terms.
"""

import sys
import os
import json
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.models.mindscape import IntentStatus

def check_workspaces(store: MindscapeStore):
    """Check workspaces for Aura CIS related content"""
    print("\n" + "="*80)
    print("檢查 Workspaces")
    print("="*80)

    # Query all workspaces directly from database
    found = False

    with store.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM workspaces')
        rows = cursor.fetchall()

        for row in rows:
            ws_id = row['id']
            title = row['title'] or ''
            description = row['description'] or ''
            mode = row['mode'] or ''
            metadata_json = row['metadata']

            title_match = 'CIS' in title or '武林逸亭' in title or 'Aura' in title
            desc_match = 'CIS' in description or '武林逸亭' in description or 'Aura' in description
            metadata_match = False
            metadata_data = {}

            # Check metadata
            if metadata_json:
                try:
                    metadata_data = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                    metadata_str = json.dumps(metadata_data, ensure_ascii=False)
                    metadata_match = 'CIS' in metadata_str or '武林逸亭' in metadata_str or 'Aura' in metadata_str
                except:
                    pass

            if title_match or desc_match or metadata_match:
                found = True
                print(f"\n找到匹配的 Workspace:")
                print(f"  ID: {ws_id}")
                print(f"  Title: {title}")
                print(f"  Description: {description or '(無)'}")
                print(f"  Mode: {mode or '(無)'}")

                if metadata_match:
                    print(f"  Metadata (包含相關內容):")
                    core_memory = metadata_data.get('core_memory', {})
                    if core_memory:
                        print(f"    Core Memory:")
                        if core_memory.get('brand_identity'):
                            print(f"      Brand Identity: {json.dumps(core_memory['brand_identity'], ensure_ascii=False)}")
                        if core_memory.get('voice_and_tone'):
                            print(f"      Voice and Tone: {json.dumps(core_memory['voice_and_tone'], ensure_ascii=False)}")

    if not found:
        print("未找到包含 'CIS'、'Aura' 或 '武林逸亭' 的 workspace")

    return found

def check_intents(store: MindscapeStore):
    """Check active intents for Aura CIS related content"""
    print("\n" + "="*80)
    print("檢查 Active Intents")
    print("="*80)

    # Query all profiles and intents directly from database
    found = False

    with store.get_connection() as conn:
        cursor = conn.cursor()
        # Get all profiles
        cursor.execute('SELECT DISTINCT profile_id FROM intents')
        profile_ids = [row['profile_id'] for row in cursor.fetchall()]

        for profile_id in profile_ids:
            try:
                cursor.execute('''
                    SELECT * FROM intents
                    WHERE profile_id = ? AND status = 'active'
                ''', (profile_id,))
                rows = cursor.fetchall()

                for row in rows:
                    title = row['title'] or ''
                    description = row['description'] or ''

                    title_match = 'CIS' in title or '武林逸亭' in title or 'Aura' in title
                    desc_match = 'CIS' in description or '武林逸亭' in description or 'Aura' in description

                    if title_match or desc_match:
                        found = True
                        print(f"\n找到匹配的 Intent:")
                        print(f"  ID: {row['id']}")
                        print(f"  Profile ID: {profile_id}")
                        print(f"  Title: {title}")
                        print(f"  Description: {description or '(無)'}")
                        print(f"  Status: {row['status']}")
                        print(f"  Priority: {row['priority'] or '(無)'}")
            except Exception as e:
                print(f"  檢查 profile {profile_id} 的 intents 時發生錯誤: {e}")

    if not found:
        print("未找到包含 'CIS'、'Aura' 或 '武林逸亭' 的 active intent")

    return found

def check_profile_memory(store: MindscapeStore):
    """Check profile memory for Aura CIS related content"""
    print("\n" + "="*80)
    print("檢查 Profile Memory")
    print("="*80)

    # Query all profiles directly from database
    found = False

    with store.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM profiles')
        rows = cursor.fetchall()

        for row in rows:
            profile_id = row['id']
            name = row['name'] or ''

            # Check if metadata column exists
            try:
                metadata_json = row['metadata']
            except (KeyError, IndexError):
                # metadata column doesn't exist in this schema version
                continue

            if metadata_json:
                try:
                    metadata_data = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                    metadata_str = json.dumps(metadata_data, ensure_ascii=False)

                    if 'CIS' in metadata_str or '武林逸亭' in metadata_str or 'Aura' in metadata_str:
                        found = True
                        print(f"\n找到匹配的 Profile:")
                        print(f"  ID: {profile_id}")
                        print(f"  Name: {name or '(無)'}")

                        workspace_memories = metadata_data.get('workspace_memories', {})
                        if workspace_memories:
                            print(f"  Workspace Memories:")
                            for ws_id, ws_memory in workspace_memories.items():
                                ws_memory_str = json.dumps(ws_memory, ensure_ascii=False)
                                if 'CIS' in ws_memory_str or '武林逸亭' in ws_memory_str or 'Aura' in ws_memory_str:
                                    print(f"    Workspace {ws_id}:")
                                    if ws_memory.get('skills'):
                                        print(f"      Skills: {ws_memory['skills']}")
                                    if ws_memory.get('preferences'):
                                        print(f"      Preferences: {json.dumps(ws_memory['preferences'], ensure_ascii=False)}")
                except Exception as e:
                    pass

    if not found:
        print("未找到包含 'CIS'、'Aura' 或 '武林逸亭' 的 profile memory")

    return found

def check_recent_events(store: MindscapeStore):
    """Check recent events for Aura CIS related content"""
    print("\n" + "="*80)
    print("檢查最近的 Events (最近 50 個)")
    print("="*80)

    # Query all workspaces and events directly from database
    found = False

    with store.get_connection() as conn:
        cursor = conn.cursor()
        # Get workspace titles for reference
        cursor.execute('SELECT id, title FROM workspaces')
        workspace_titles = {row['id']: row['title'] for row in cursor.fetchall()}

        # Get recent events
        cursor.execute('''
            SELECT e.*, e.payload, e.metadata
            FROM mind_events e
            ORDER BY e.timestamp DESC
            LIMIT 100
        ''')
        rows = cursor.fetchall()

        for row in rows:
            try:
                event_id = row['id']
                workspace_id = row['workspace_id']
                event_type = row['event_type']
                actor = row['actor']
                timestamp = row['timestamp']
                payload_json = row['payload']
                metadata_json = row['metadata']

                # Parse JSON
                payload_data = {}
                metadata_data = {}
                try:
                    payload_data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
                    metadata_data = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                except:
                    pass

                # Check payload
                payload_str = json.dumps(payload_data, ensure_ascii=False) if payload_data else str(payload_json or '')
                metadata_str = json.dumps(metadata_data, ensure_ascii=False) if metadata_data else str(metadata_json or '')

                if 'CIS' in payload_str or '武林逸亭' in payload_str or 'Aura' in payload_str or \
                   'CIS' in metadata_str or '武林逸亭' in metadata_str or 'Aura' in metadata_str:
                    found = True
                    ws_title = workspace_titles.get(workspace_id, '(未知)')
                    print(f"\n找到匹配的 Event:")
                    print(f"  ID: {event_id}")
                    print(f"  Workspace ID: {workspace_id} ({ws_title})")
                    print(f"  Event Type: {event_type}")
                    print(f"  Actor: {actor}")
                    print(f"  Timestamp: {timestamp}")

                    if isinstance(payload_data, dict):
                        message = payload_data.get('message', '')
                        if message and ('CIS' in message or '武林逸亭' in message or 'Aura' in message):
                            print(f"  Message (前 200 字): {message[:200]}")
            except Exception as e:
                print(f"  處理 event 時發生錯誤: {e}")

    if not found:
        print("未找到包含 'CIS'、'Aura' 或 '武林逸亭' 的最近 events")

    return found

def main():
    """Main investigation function"""
    print("="*80)
    print("Aura CIS 歡迎語問題調查")
    print("="*80)
    print("\n正在檢查資料庫中的相關資料...")

    try:
        store = MindscapeStore()

        results = {
            'workspaces': check_workspaces(store),
            'intents': check_intents(store),
            'profile_memory': check_profile_memory(store),
            'recent_events': check_recent_events(store)
        }

        print("\n" + "="*80)
        print("調查結果總結")
        print("="*80)

        total_found = sum(1 for v in results.values() if v)

        if total_found == 0:
            print("\n✅ 未在資料庫中找到任何包含 'CIS'、'Aura' 或 '武林逸亭' 的資料")
            print("\n這表示問題可能來自：")
            print("  1. LLM 模型本身的訓練資料或知識庫")
            print("  2. 其他外部資料來源（如 RAG 向量資料庫）")
            print("  3. 系統 prompt 或其他配置檔案")
        else:
            print(f"\n⚠️  在 {total_found} 個資料來源中發現相關內容：")
            for key, found in results.items():
                status = "✅ 發現" if found else "❌ 未發現"
                print(f"  - {key}: {status}")

        print("\n" + "="*80)

    except Exception as e:
        print(f"\n❌ 調查過程中發生錯誤: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()



#!/usr/bin/env python3
"""
Fix existing project flows by adding playbook_sequence using LLM
"""

import sys
import asyncio
from pathlib import Path

# Add workspace root to path
WORKSPACE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.project.project_detector import ProjectDetector
from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
from backend.app.models.playbook_flow import PlaybookFlow
from datetime import datetime

WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"

async def fix_project_flows():
    """Fix existing project flows by adding playbook_sequence"""
    print("=" * 80)
    print("修復現有專案的 Flow Playbook 序列")
    print("=" * 80)
    print()

    # Initialize stores
    store = MindscapeStore()
    project_manager = ProjectManager(store=store)
    project_detector = ProjectDetector()
    flows_store = PlaybookFlowsStore(db_path=store.db_path)

    # Get all open projects
    projects = await project_manager.list_projects(
        workspace_id=WORKSPACE_ID,
        state="open"
    )

    print(f"找到 {len(projects)} 個專案\n")

    fixed = 0
    created = 0
    skipped = 0
    errors = 0

    for project in projects:
        project_id = project.id
        project_title = project.title
        project_type = project.type
        flow_id = project.flow_id

        print(f"專案: {project_title[:40]}")
        print(f"  類型: {project_type}")
        print(f"  Flow ID: {flow_id}")

        if not flow_id:
            print(f"  ⚠️  跳過：沒有 flow_id")
            skipped += 1
            print()
            continue

        # Get or create flow
        flow = flows_store.get_flow(flow_id)

        # Use LLM to suggest playbook_sequence based on project
        #
        # 補充方式說明：
        # 1. 基於專案的實際資訊（title, type）讓 LLM 分析
        # 2. 這不是"猜"，而是使用專案創建時已有的資訊
        # 3. 如果專案是從 intent_extraction 創建的，metadata 中可能有 primary_intent
        # 4. 但即使沒有，專案的 title 和 type 已經足夠讓 LLM 判斷需要的 playbook
        #
        # 例如：
        # - "十本手帳開箱內容企劃" (content_campaign) → LLM 會建議 content_drafting, content_editing 等
        # - "Mindscape Book 2025" (book) → LLM 會建議 yearly_personal_book 等
        try:
            # Build message for LLM analysis
            # Use project title and type as primary information
            message = f"{project_title}"
            if project_type:
                message += f" (type: {project_type})"

            # Check metadata for additional context
            if project.metadata and isinstance(project.metadata, dict):
                primary_intent = project.metadata.get('primary_intent')
                if primary_intent:
                    message += f"\n\nOriginal intent: {primary_intent}"
                    print(f"  ℹ️  找到原始 Intent: {primary_intent[:50]}")

            # Get workspace for context
            from backend.app.services.stores.workspaces_store import WorkspacesStore
            workspaces_store = WorkspacesStore(db_path=store.db_path)
            workspace = workspaces_store.get_workspace(WORKSPACE_ID)

            # Detect project suggestion (this will use LLM to suggest playbook_sequence)
            # Based on the actual project information (title, type, metadata)
            print(f"  🔍 使用 LLM 分析專案資訊，建議 playbook 序列...")
            suggestion = await project_detector.detect(
                message=message,
                conversation_context=[],
                workspace=workspace
            )

            if not suggestion or suggestion.mode != "project":
                print(f"  ⚠️  LLM 未識別為專案，使用空序列")
                playbook_sequence = []
            else:
                playbook_sequence = suggestion.playbook_sequence or []
                print(f"  ✓ LLM 基於專案資訊分析，建議 {len(playbook_sequence)} 個 playbooks")
                if playbook_sequence:
                    print(f"    {', '.join(playbook_sequence)}")
                else:
                    print(f"    (LLM 未建議任何 playbook)")

        except Exception as e:
            print(f"  ⚠️  LLM 分析錯誤: {str(e)[:50]}，使用空序列")
            import traceback
            traceback.print_exc()
            playbook_sequence = []

        # Update or create flow
        if flow:
            # Update existing flow
            flow_def = flow.flow_definition or {}
            if not isinstance(flow_def, dict):
                flow_def = {}

            # Update playbook_sequence
            flow_def['playbook_sequence'] = playbook_sequence
            flow.flow_definition = flow_def
            flow.updated_at = datetime.utcnow()

            flows_store.update_flow(flow)
            print(f"  ✓ 已更新 flow，playbook 序列: {len(playbook_sequence)}")
            fixed += 1
        else:
            # Create new flow
            flow = PlaybookFlow(
                id=flow_id,
                name=f"{project_type.replace('_', ' ').title()} Flow",
                description=f"Flow for {project_type} projects",
                flow_definition={
                    "nodes": [],
                    "edges": [],
                    "playbook_sequence": playbook_sequence
                },
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            flows_store.create_flow(flow)
            print(f"  ✓ 已創建 flow，playbook 序列: {len(playbook_sequence)}")
            created += 1

        print()

    print("=" * 80)
    print(f"完成：更新 {fixed} 個，創建 {created} 個，跳過 {skipped} 個，錯誤 {errors} 個")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(fix_project_flows())


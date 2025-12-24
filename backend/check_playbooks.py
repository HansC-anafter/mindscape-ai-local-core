"""Check playbooks in Docker environment"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

from app.services.playbook_service import PlaybookService
from app.services.mindscape_store import MindscapeStore
from app.services.playbook.playbook_scope_resolver import PlaybookScopeResolver

async def check_playbooks():
    store = MindscapeStore()
    ps = PlaybookService(store)

    # Check all playbooks
    playbooks = await ps.list_playbooks(workspace_id=None)
    print(f"Total playbooks: {len(playbooks)}")

    # Check structure of first playbook
    if playbooks:
        first = playbooks[0]
        print(f"First playbook type: {type(first)}")
        print(f"First playbook attributes: {dir(first)[:10]}")
        if hasattr(first, 'playbook'):
            print(f"First playbook code: {first.playbook.metadata.playbook_code if hasattr(first.playbook, 'metadata') else 'N/A'}")
        elif hasattr(first, 'metadata'):
            print(f"First playbook code: {first.metadata.playbook_code if hasattr(first.metadata, 'playbook_code') else 'N/A'}")

    # PlaybookMetadata has playbook_code directly
    ig_playbooks = [p for p in playbooks if hasattr(p, 'playbook_code') and 'ig_' in p.playbook_code]
    print(f"IG playbooks count: {len(ig_playbooks)}")
    if ig_playbooks:
        print(f"  First 5 codes: {[p.playbook_code for p in ig_playbooks[:5]]}")

    # Check effective playbooks for test workspace
    scope_resolver = PlaybookScopeResolver(store)
    effective = await scope_resolver.resolve_effective_playbooks(
        tenant_id=None,
        workspace_id="test-workspace-id",
        user_id="test-user-id",
        project_id=None
    )
    print(f"Effective playbooks for test-workspace-id: {len(effective)}")
    if effective:
        print(f"  First 5: {[p.get('playbook_code') for p in effective[:5]]}")

    # Check with None workspace
    effective_none = await scope_resolver.resolve_effective_playbooks(
        tenant_id=None,
        workspace_id=None,
        user_id="test-user-id",
        project_id=None
    )
    print(f"Effective playbooks for None workspace: {len(effective_none)}")
    if effective_none:
        print(f"  First 5: {[p.get('playbook_code') for p in effective_none[:5]]}")

if __name__ == "__main__":
    asyncio.run(check_playbooks())


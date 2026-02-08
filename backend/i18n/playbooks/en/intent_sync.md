---
playbook_code: intent_sync
version: 2.0.0
locale: en
name: "Intent Sync"
description: "Read all active IntentCards in the workspace, calculate intent_drift (direction changes) and intent_density (crowding level), and automatically adjust collection strategy."
capability_code: frontier_research
tags:
  - research
  - intent
  - automation
---

# Intent Sync

## Overview
Read all active IntentCards in the workspace, calculate intent drift and density, automatically adjust collection strategy and create intent snapshots.

## What problem does this playbook solve?
Your research intents change weekly, but if the collection strategy remains fixed, it leads to:
- Direction changed but still collecting old content (waste of time)
- Asking too many similar questions (information redundancy)
- Important intents lack corresponding materials (gaps)

## Corresponding Existing Systems

| Model Used | Purpose |
|------------|---------|
| `IntentCard` | Read title, description, tags, storyline_tags, metadata.questions |
| `Workspace.metadata.research_config` | Read/write collection strategy configuration |
| `Artifact (intent_snapshot)` | Store intent snapshots for drift calculation |

## Inputs
- `workspace_id`: Workspace ID (single workspace mode, backward compatible)
- `group_id`: Workspace Group ID (group-level execution, new)
- `workspace_ids`: List of Workspace IDs (explicitly specify multiple workspaces, new)
- `force_recalculate`: Whether to force recalculation (default: false)

**Execution Modes**:
- If `group_id` is provided: Execute at group level, automatically retrieve intents from all workspaces in the group
- If `workspace_ids` is provided: Process specified multiple workspaces
- If only `workspace_id` is provided: Single workspace mode (backward compatible)

## Execution Logic

```python
import numpy as np
from sklearn.preprocessing import normalize
from sklearn.metrics.pairwise import cosine_similarity
import hdbscan
from datetime import datetime, timedelta

# 0. Parse input parameters
workspace_id = inputs.get("workspace_id")
group_id = inputs.get("group_id")
workspace_ids = inputs.get("workspace_ids")

# 1. Determine workspace list to process
if group_id:
    # Group-level execution: Get all workspaces in the group
    # ⚠️ Use WorkspaceGroupAdapter (Cloud version)
    try:
        from capabilities.frontier_research.services.workspace_group_adapter import get_workspace_group_adapter

        # Get adapter (requires db_session, obtained from execution_context)
        # ⚠️ In actual usage, need to get db_session from execution_context
        adapter = get_workspace_group_adapter(db_session=execution_context.get("db_session"))

        if adapter:
            workspace_ids = await adapter.get_group_workspace_ids(group_id)
            if not workspace_ids:
                logger.warning(f"Workspace Group {group_id} has no workspaces, falling back to workspace_id")
                workspace_ids = [workspace_id] if workspace_id else []
        else:
            # Local-Core doesn't support, fallback to single workspace
            logger.info(f"Workspace Group not supported (Local-Core?), using single workspace")
            workspace_ids = [workspace_id] if workspace_id else []
    except Exception as e:
        logger.warning(f"Failed to get workspace group workspaces: {e}, falling back to single workspace")
        workspace_ids = [workspace_id] if workspace_id else []
elif workspace_ids:
    # Explicitly specify multiple workspaces
    workspace_ids = workspace_ids
else:
    # Single workspace mode (backward compatible)
    workspace_ids = [workspace_id] if workspace_id else []

# 2. Collect active IntentCards from all workspaces
all_intents = []
for ws_id in workspace_ids:
    intents = await intents_store.list(
        workspace_id=ws_id,
        status="active",
        updated_since=datetime.now() - timedelta(days=30)
    )
    all_intents.extend(intents)

intents = all_intents

# 3. Read previous intent snapshots (⚠️ Get latest for each intent separately)
# If at group level, read from primary workspace (or support group-level snapshot)
primary_workspace_id = workspace_ids[0] if workspace_ids else workspace_id
# ⚠️ get_latest is a synchronous method (not async)
snapshot_map = {}
for intent in intents:
    snapshot = artifact_store.get_latest(
        workspace_id=primary_workspace_id,  # Use primary workspace
        artifact_type=ArtifactType.INTENT_SNAPSHOT,
        filter={"content.intent_id": intent.id},
        order_by="-created_at"
    )
    if snapshot and snapshot.content:
        snapshot_map[intent.id] = snapshot  # Store entire artifact, not just content
```

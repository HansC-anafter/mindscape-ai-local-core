---
playbook_code: evidence_pack
version: 2.0.0
locale: en
name: "Evidence Pack Generator"
description: "Generate evidence packs for each intent: supporting evidence (forward filtering results), opposing evidence (reverse filtering results), gap analysis (Missing Evidence), and next steps recommendations."
capability_code: frontier_research
tags:
  - research
  - evidence
  - analysis
---

# Evidence Pack Generator

## Overview
Generate decision-ready evidence packs for each active intent in the workspace, including drift/density summaries, supporting evidence, opposing evidence (with contrarian_reason), gap analysis, and next steps recommendations.

## What problem does this playbook solve?
You have a pile of materials, but:
- Don't know which ones support your arguments
- Don't know what the opposing side says, and **why they are opposing**
- Don't know what's still missing
- Still start from scratch every time you need to write something

**Evidence packs** pre-organize all of this into "decision-ready inputs".

## Corresponding Existing Systems

| Model Used | Purpose |
|------------|---------|
| `IntentCard` | Read intent goals and progress_percentage |
| `Artifact (evidence_pack)` | Store evidence packs |
| `Artifact (intent_snapshot)` | Read drift/density data |
| `ArtifactProvenance` | Track evidence pack generation context |
| `research_config` | Read current collection mode |

## Inputs
- `workspace_id`: Workspace ID (single workspace mode, backward compatible)
- `group_id`: Workspace Group ID (group-level execution, new)
- `workspace_ids`: List of Workspace IDs (explicitly specify multiple workspaces, new)
- `target_intents`: List of intent IDs to specify (optional, default: process all active)
- `time_range`: Time range (optional, default: last 7 days)

**Execution Modes**:
- If `group_id` is provided: Execute at group level, aggregate evidence from all workspaces in the group
- If `workspace_ids` is provided: Process specified multiple workspaces
- If only `workspace_id` is provided: Single workspace mode (backward compatible)

## Execution Logic

```python
# 0. Parse input parameters
workspace_id = inputs.get("workspace_id")
group_id = inputs.get("group_id")
workspace_ids = inputs.get("workspace_ids")

# 1. Read research_config (know current mode)
research_config = workspace.metadata.get("research_config", {})
current_mode = research_config.get("mode", "steady")

# 2. Determine workspace list to process (same logic as intent_sync)
if group_id:
    # Group-level execution: Get all workspaces in the group
    try:
        from capabilities.frontier_research.services.workspace_group_adapter import get_workspace_group_adapter

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
    workspace_ids = workspace_ids
else:
    workspace_ids = [workspace_id] if workspace_id else []

primary_workspace_id = workspace_ids[0] if workspace_ids else workspace_id

# 3. Collect active IntentCards from all workspaces
all_intents = []
for ws_id in workspace_ids:
    intents = await intents_store.list(
        workspace_id=ws_id,
        status="active"
    )
    all_intents.extend(intents)

if target_intents:
    intents = [i for i in intents if i.id in target_intents]

# 4. Read latest intent_snapshot (get drift/density)
# ⚠️ get_latest is a synchronous method (not async)
snapshot_map = {}
for intent in intents:
    snapshot = artifact_store.get_latest(
        workspace_id=primary_workspace_id,  # Use primary workspace
        artifact_type=ArtifactType.INTENT_SNAPSHOT,
        filter={"content.intent_id": intent.id}
    )
    if snapshot:
        snapshot_map[intent.id] = snapshot.content

# 5. Collect newly added materials this week (already passed through lens_filter, support cross-workspace)
time_range = inputs.get("time_range", {"days": 7})
start_date = datetime.now() - timedelta(days=time_range.get("days", 7))

filtered_materials = []
for ws_id in workspace_ids:
    materials = await artifact_store.list(
        workspace_id=ws_id,
        artifact_type=ArtifactType.LENS_FILTERED_MATERIAL,
        filter={
            "created_at": {"$gte": start_date.isoformat()},
            "content.lens_tags": {"$exists": True}
        }
    )
    filtered_materials.extend(materials)

# 6. Group materials by intent (using intent_id in material metadata)
intent_materials = {}
for material in filtered_materials:
    intent_id = material.content.get("intent_id")
    if intent_id:
        if intent_id not in intent_materials:
            intent_materials[intent_id] = []
        intent_materials[intent_id].append(material)

# 7. Generate evidence pack for each intent
evidence_packs = []
for intent in intents:
    intent_id = intent.id
    materials = intent_materials.get(intent_id, [])
    snapshot = snapshot_map.get(intent_id)

    # Separate supporting and opposing evidence
    supporting = [m for m in materials if not m.content.get("contrarian", False)]
    opposing = [m for m in materials if m.content.get("contrarian", False)]

    # Generate pack content
    pack_content = {
        "intent_id": intent_id,
        "intent_title": intent.title,
        "drift_summary": snapshot.get("drift_summary") if snapshot else None,
        "density_summary": snapshot.get("density_summary") if snapshot else None,
        "current_mode": current_mode,
        "supporting_evidence": [
            {
                "material_id": m.id,
                "source_title": m.content.get("source_title"),
                "source_url": m.content.get("source_url"),
                "claims": m.content.get("claims", []),
                "lens_tags": m.content.get("lens_tags", {})
            }
            for m in supporting
        ],
        "opposing_evidence": [
            {
                "material_id": m.id,
                "source_title": m.content.get("source_title"),
                "source_url": m.content.get("source_url"),
                "claims": m.content.get("claims", []),
                "lens_tags": m.content.get("lens_tags", {}),
                "contrarian_reason": m.content.get("contrarian_reason")
            }
            for m in opposing
        ],
        "gap_analysis": await analyze_gaps(intent, supporting, opposing),
        "next_steps": await generate_next_steps(intent, snapshot, supporting, opposing)
    }

    evidence_packs.append(pack_content)

# 8. Create Artifact for each evidence pack
for pack_content in evidence_packs:
    await artifact_store.create(
        workspace_id=primary_workspace_id,
        artifact_type=ArtifactType.EVIDENCE_PACK,
        content=pack_content
    )
```

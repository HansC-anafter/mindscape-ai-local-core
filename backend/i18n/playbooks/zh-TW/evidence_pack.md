---
playbook_code: evidence_pack
version: 2.0.0
locale: zh-TW
name: "證據包生成"
description: "為每個意圖生成證據包：支撐證據（正向過濾結果）、反方證據（反向過濾結果）、缺口分析（Missing Evidence）、下一步建議。"
capability_code: frontier_research
tags:
  - research
  - evidence
  - analysis
---

# 證據包生成

## 概述
為 workspace 內每個活躍意圖生成可決策的證據包，包含 drift/density 摘要、支撐證據、反方證據（含 contrarian_reason）、缺口分析和下一步建議。

## 這個 playbook 解決什麼問題？
有一堆材料，但：
- 不知道哪些支撐你的論點
- 不知道反方怎麼說，以及**為什麼是反方**
- 不知道還缺什麼
- 每次要寫東西還是從零開始整理

**證據包**把這些都預先整理好，變成「可決策的輸入」。

## 對應現有系統

| 使用模型 | 用途 |
|----------|------|
| `IntentCard` | 讀取意圖目標和 progress_percentage |
| `Artifact (evidence_pack)` | 儲存證據包 |
| `Artifact (intent_snapshot)` | 讀取 drift/density 數據 |
| `ArtifactProvenance` | 追蹤證據包的生成上下文 |
| `research_config` | 讀取當前搜集模式 |

## 輸入
- `workspace_id`: Workspace ID（單一 workspace 模式，向後兼容）
- `group_id`: Workspace Group ID（Group 層級執行，新增）
- `workspace_ids`: Workspace ID 列表（明確指定多個 workspace，新增）
- `target_intents`: 指定意圖 ID 列表（可選，預設處理所有 active）
- `time_range`: 時間範圍（可選，預設最近 7 天）

**執行模式**：
- 如果提供 `group_id`：在 Group 層級執行，聚合該 group 下所有 workspace 的證據
- 如果提供 `workspace_ids`：處理指定的多個 workspace
- 如果只提供 `workspace_id`：單一 workspace 模式（向後兼容）

## 執行邏輯

```python
# 0. 解析輸入參數
workspace_id = inputs.get("workspace_id")
group_id = inputs.get("group_id")
workspace_ids = inputs.get("workspace_ids")

# 1. 讀取 research_config（知道當前模式）
research_config = workspace.metadata.get("research_config", {})
current_mode = research_config.get("mode", "steady")

# 2. 確定要處理的 workspace 列表（與 intent_sync 相同邏輯）
if group_id:
    # Group 層級執行：獲取 group 下所有 workspace
    try:
        from capabilities.frontier_research.services.workspace_group_adapter import get_workspace_group_adapter

        adapter = get_workspace_group_adapter(db_session=execution_context.get("db_session"))

        if adapter:
            workspace_ids = await adapter.get_group_workspace_ids(group_id)
            if not workspace_ids:
                logger.warning(f"Workspace Group {group_id} has no workspaces, falling back to workspace_id")
                workspace_ids = [workspace_id] if workspace_id else []
        else:
            # Local-Core 不支持，fallback 到單一 workspace
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

# 3. 從所有 workspace 收集 active IntentCard
all_intents = []
for ws_id in workspace_ids:
    intents = await intents_store.list(
        workspace_id=ws_id,
        status="active"
    )
    all_intents.extend(intents)

if target_intents:
    intents = [i for i in intents if i.id in target_intents]

# 4. 讀取最新的 intent_snapshot（取 drift/density）
# ⚠️ get_latest 是同步方法（不是 async）
snapshot_map = {}
for intent in intents:
    snapshot = artifact_store.get_latest(
        workspace_id=primary_workspace_id,  # 使用主 workspace
        artifact_type=ArtifactType.INTENT_SNAPSHOT,
        filter={"content.intent_id": intent.id}
    )
    if snapshot:
        snapshot_map[intent.id] = snapshot.content

# 5. 收集本週新增的材料（已通過 lens_filter，支持跨 workspace）
# ⚠️ list 是同步方法（不是 async）
# 如果是多 workspace，需要合併結果
all_materials = []
for ws_id in workspace_ids:
    materials = artifact_store.list(
        workspace_id=ws_id,
        artifact_type="research_material",
        since=datetime.now() - timedelta(days=time_range.get("days_back", 7))
    )
    all_materials.extend(materials)
materials = all_materials

# 5. 為每個意圖生成證據包
evidence_packs = []
for intent in intents:
    # 從 snapshot 讀取 drift/density
    snapshot_data = snapshot_map.get(intent.id, {})
    drift = snapshot_data.get("drift", 0)
    density = snapshot_data.get("density", 0)

    # 找到與此意圖相關的材料
    relevant_materials = match_materials_to_intent(materials, intent)

    # 分類：支撐 vs 反方（用 contrarian 規則）
    supporting = []
    contrasting = []

    intent_lens_tags = intent.metadata.get("lens_tags", {})
    intent_stances = intent.metadata.get("stances", {})

    for m in relevant_materials:
        filter_status = m.get("filter_status", {})
        if filter_status.get("is_contrarian"):
            # ⚠️ 確保 contrarian_reason 已填入
            contrarian_reason = filter_status.get("contrarian_reason")
            if contrarian_reason:
                m["contrarian_reason"] = contrarian_reason
            else:
                # 備援：重新計算 contrarian_reason
                m["contrarian_reason"] = compute_contrarian_reason(
                    m.get("lens_tags", {}),
                    m.get("claims", []),
                    intent_lens_tags,
                    intent_stances
                )
            contrasting.append(m)
        elif filter_status.get("include_match"):
            supporting.append(m)

    # 確保至少 min_contrarian_per_intent 則
    min_contrarian = research_config.get("weekly_budget", {}).get("min_contrarian_per_intent", 2)
    missing_contrarian_count = 0

    if len(contrasting) < min_contrarian:
        # 調用 LensTaggingService.select_contrarians() 補足
        result = await lens_tagging_service.select_contrarians(
            materials=relevant_materials,
            intent_id=intent.id,
            current_lens_tags=intent_lens_tags,
            current_stances=intent_stances
        )

        # ⚠️ 確保補回的材料有填 contrarian_reason
        for c in result.contrarians:
            if not c.get("contrarian_reason"):
                c["contrarian_reason"] = compute_contrarian_reason(
                    c.get("lens_tags", {}),
                    c.get("claims", []),
                    intent_lens_tags,
                    intent_stances
                )

        contrasting.extend(result.contrarians)
        missing_contrarian_count = result.missing_count

    # 分析缺口
    missing = await analyze_missing_evidence(intent, relevant_materials)
    if missing_contrarian_count > 0:
        missing.append({
            "gap_type": "contrarian",
            "description": f"缺少 {missing_contrarian_count} 則反方材料",
            "why_important": "需要對照觀點以避免 confirmation bias",
            "priority": "high"
        })

    # 生成下一步建議
    next_actions = await generate_next_actions(
        intent=intent,
        supporting=supporting,
        contrasting=contrasting,
        missing=missing,
        current_mode=current_mode
    )

    # 構建證據包內容
    pack_content = {
        "intent_id": intent.id,
        "workspace_id": intent.workspace_id if hasattr(intent, 'workspace_id') else primary_workspace_id,
        "group_id": group_id if group_id else None,  # Group 層級標記
        "workspace_ids": workspace_ids if len(workspace_ids) > 1 else None,  # 多 workspace 標記
        "intent_title": intent.title,
        "intent_status": intent.status.value,
        # ⚠️ 使用 progress_percentage（不是 progress）
        "intent_progress": intent.progress_percentage,

        # drift/density 摘要
        "drift_since_last_pack": drift,
        "density": density,

        # 支撐證據
        "supporting_evidence": [
            {
                "material_id": m["material_id"],
                "source_title": m["source_title"],
                "source_url": m.get("source_url"),
                "claim_text_zh": m["claims"][0]["claim_text_zh"] if m.get("claims") else None,
                # lens_tags 是維度→值
                "lens_tags": m.get("lens_tags", {}),
                "evidence_type": m["claims"][0].get("evidence_type") if m.get("claims") else None,
                # 用 block_id 錨定
                "evidence_spans": m["claims"][0].get("evidence_spans", []) if m.get("claims") else []
            }
            for m in supporting[:5]  # 最多 5 則
        ],

        # 反方證據
        "contrasting_evidence": [
            {
                "material_id": m["material_id"],
                "source_title": m["source_title"],
                "source_url": m.get("source_url"),
                "claim_text_zh": m["claims"][0]["claim_text_zh"] if m.get("claims") else None,
                "lens_tags": m.get("lens_tags", {}),
                # ⚠️ contrarian_reason 必填（說明為什麼是反方）
                "contrarian_reason": m.get("contrarian_reason", "unknown"),
                "evidence_spans": m["claims"][0].get("evidence_spans", []) if m.get("claims") else []
            }
            for m in contrasting[:3]  # 最多 3 則
        ],

        # 缺口分析
        "missing_evidence": missing,

        # 下一步建議
        "next_actions": next_actions,

        # 分歧摘要（如果有相關的 disagreement_brief）
        "disagreement_summary": await get_related_disagreements(intent.id)
    }

    evidence_packs.append(pack_content)

# =====================
# 輔助函數：計算 contrarian_reason
# =====================
def compute_contrarian_reason(
    material_lens_tags: Dict,
    material_claims: List[Dict],
    intent_lens_tags: Dict,
    intent_stances: Dict
) -> str:
    """
    計算 contrarian_reason

    優先級：
    1. stance.position opposite
    2. lens pair 對立
    """
    CONTRARIAN_PAIRS = {
        "governance_orientation": ["control_plane", "tooling"],
        "evaluation_orientation": ["benchmark", "auditing"],
        "collaboration_model": ["human_primary", "agent_primary"]
    }

    # 優先檢查 stance opposite
    for claim in material_claims:
        stance = claim.get("stance", {})
        proposition = stance.get("proposition", "")
        position = stance.get("position", "")

        if proposition in intent_stances:
            intent_position = intent_stances[proposition]
            if (position == "support" and intent_position == "oppose") or \
               (position == "oppose" and intent_position == "support"):
                return f"stance.position opposite on '{proposition}': {intent_position} vs {position}"

    # 檢查 lens pair 對立
    for dim, pair in CONTRARIAN_PAIRS.items():
        material_val = material_lens_tags.get(dim)
        intent_val = intent_lens_tags.get(dim)

        if material_val and intent_val:
            if material_val in pair and intent_val in pair and material_val != intent_val:
                return f"{dim}: {intent_val} vs {material_val}"

    return "unknown"

# 6. 創建 Artifact（使用主 workspace）
primary_workspace_id = workspace_ids[0] if workspace_ids else workspace_id

artifact = Artifact(
    workspace_id=primary_workspace_id,  # 使用主 workspace
    artifact_type=ArtifactType.EVIDENCE_PACK,
    title=f"Evidence Pack - Week of {datetime.now().strftime('%Y-%m-%d')}",
    content={
        "artifact_id": str(uuid.uuid4()),
        "generated_at": datetime.now().isoformat(),

        # research_config 模式輸出
        "summary": {
            "materials_processed": len(materials),
            "mode_used": current_mode
        },

        "intents": evidence_packs
    }
)

# 記錄溯源
provenance = ArtifactProvenance(
    execution_id=current_execution_id,
    step_id="evidence_pack_generation",
    context_hash=hashlib.sha256(
        f"{workspace_id}{[i.id for i in intents]}{len(materials)}".encode()
    ).hexdigest(),
    layers_used=[lens.id for lens in used_lenses],
    compiled_context_snapshot={
        "intent_count": len(intents),
        "materials_count": len(materials),
        "time_range": time_range,
        "research_config": research_config
    }
)

await artifact_store.create(artifact, provenance=provenance)
```

## 輸出

```yaml
artifact_type: evidence_pack
artifact_id: "ep_001"
workspace_id: "ws_001"
generated_at: "2026-01-01T12:00:00Z"

# 搜集模式摘要
summary:
  materials_processed: 18
  mode_used: "steady"  # broaden | narrow | steady

# 溯源資訊
provenance:
  execution_id: "exec_001"
  layers_used:
    - "research_lens.control_plane"
    - "research_lens.human_centered"
  context_snapshot:
    intent_count: 2
    materials_count: 18
    research_config:
      mode: "steady"
      weekly_budget:
        max_materials: 30
        min_contrarian_per_intent: 2

# 每個意圖的證據包
intents:
  - intent_id: "intent_001"
    title: "搞懂 multi-agent 的 human-in-the-loop 最佳實踐"
    intent_status: "active"
    # ⚠️ 使用 progress_percentage
    intent_progress: 40

    # drift/density 摘要
    drift_since_last_pack: 0.12
    density: 2.3

    # 支撐證據
    supporting_evidence:
      - material_id: "m_001"
        source_title: "LangGraph 0.3.0 Release Notes"
        source_url: "https://..."
        claim_text_zh: "interrupt_before/after 是標準的 HITL 原語"
        # lens_tags 是維度→值
        lens_tags:
          governance_orientation: "control_plane"
          evaluation_orientation: "human_centered"
        evidence_type: "documentation"
        # 用 block_id 錨定
        evidence_spans:
          - block_id: "p_003"
            original_text: "Use interrupt_before to pause the graph..."

    # 反方證據
    contrasting_evidence:
      - material_id: "m_005"
        source_title: "AutoGen Blog Post"
        source_url: "https://..."
        claim_text_zh: "過多的人工介入會拖慢 agent 效率"
        lens_tags:
          governance_orientation: "tooling"
          collaboration_model: "agent_primary"
        # ⚠️ contrarian_reason 必填
        contrarian_reason: "governance_orientation: control_plane vs tooling"
        evidence_spans:
          - block_id: "p_007"
            original_text: "The goal is to minimize human intervention..."

      - material_id: "m_008"
        source_title: "Some Automation Paper"
        source_url: "https://..."
        claim_text_zh: "HITL 不應該是強制的"
        lens_tags:
          governance_orientation: "orchestration"
        # ⚠️ stance opposite 的 reason 更明確
        contrarian_reason: "stance.position opposite on 'HITL should be structurally enforced': support vs oppose"
        evidence_spans:
          - block_id: "p_012"
            original_text: "Mandatory HITL creates bottlenecks..."

    # 分歧摘要（連結到 disagreement_brief）
    disagreement_summary:
      most_significant:
        proposition: "HITL should be structurally enforced"
        summary_zh: "LangGraph 強制 HITL，AutoGen 最小化介入"
        brief_id: "db_001"

    # 缺口分析
    missing_evidence:
      - gap_type: "case_study"
        description: "缺少實際部署案例"
        why_important: "需要知道實際部署時的 HITL 開銷"
        priority: "high"

    # 下一步建議
    next_actions:
      - action: "找 production 案例"
        priority: "high"
        reason: "缺口分析顯示需要實際案例"
        suggested_approach: "在 LangSmith/Langfuse 社群問"
```

## 證據包的使用場景

1. **每週 review**：快速掌握研究進度，知道 drift/density 趨勢
2. **寫作前準備**：不用從零整理材料，直接用 supporting/contrasting
3. **決策支持**：知道支撐/反方/缺口，以及**為什麼是反方**
4. **進度追蹤**：配合 IntentCard.progress_percentage 更新

## 依賴

| 服務 | 用途 |
|------|------|
| `IntentDriftService` | 讀取 drift/density（從 intent_snapshot） |
| `LensTaggingService` | 補足 contrarian 材料（確保有 contrarian_reason） |
| `artifact_store` | 創建 evidence_pack Artifact |

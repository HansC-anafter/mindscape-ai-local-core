---
playbook_code: intent_sync
version: 2.0.0
locale: zh-TW
name: "意圖同步"
description: "讀取 workspace 內所有 active IntentCard，計算 intent_drift（方向變動）和 intent_density（擁擠程度），自動調整搜集策略。"
capability_code: frontier_research
tags:
  - research
  - intent
  - automation
---

# 意圖同步

## 概述
讀取 workspace 內所有 active IntentCard，計算意圖漂移（drift）和密集度（density），自動調整搜集策略並創建意圖快照。

## 這個 playbook 解決什麼問題？
你的研究意圖每週都在變動，但搜集策略如果固定不變，會導致：
- 方向變了但還在抓舊東西（浪費時間）
- 問太多類似的問題（資訊重複）
- 重要的意圖沒有對應的材料（缺口）

## 對應現有系統

| 使用模型 | 用途 |
|----------|------|
| `IntentCard` | 讀取 title, description, tags, storyline_tags, metadata.questions |
| `Workspace.metadata.research_config` | 讀寫搜集策略配置 |
| `Artifact (intent_snapshot)` | 儲存意圖快照供 drift 計算 |

## 輸入
- `workspace_id`: Workspace ID（單一 workspace 模式，向後兼容）
- `group_id`: Workspace Group ID（Group 層級執行，新增）
- `workspace_ids`: Workspace ID 列表（明確指定多個 workspace，新增）
- `force_recalculate`: 是否強制重新計算（預設: false）

**執行模式**：
- 如果提供 `group_id`：在 Group 層級執行，自動獲取該 group 下所有 workspace 的意圖
- 如果提供 `workspace_ids`：處理指定的多個 workspace
- 如果只提供 `workspace_id`：單一 workspace 模式（向後兼容）

## 執行邏輯

```python
import numpy as np
from sklearn.preprocessing import normalize
from sklearn.metrics.pairwise import cosine_similarity
import hdbscan
from datetime import datetime, timedelta

# 0. 解析輸入參數
workspace_id = inputs.get("workspace_id")
group_id = inputs.get("group_id")
workspace_ids = inputs.get("workspace_ids")

# 1. 確定要處理的 workspace 列表
if group_id:
    # Group 層級執行：獲取 group 下所有 workspace
    # ⚠️ 使用 WorkspaceGroupAdapter（Cloud 版本）
    try:
        from capabilities.frontier_research.services.workspace_group_adapter import get_workspace_group_adapter

        # 獲取適配器（需要 db_session，從 execution_context 獲取）
        # ⚠️ 實際使用時需要從 execution_context 獲取 db_session
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
    # 明確指定多個 workspace
    workspace_ids = workspace_ids
else:
    # 單一 workspace 模式（向後兼容）
    workspace_ids = [workspace_id] if workspace_id else []

# 2. 從所有 workspace 收集 active IntentCard
all_intents = []
for ws_id in workspace_ids:
    intents = await intents_store.list(
        workspace_id=ws_id,
        status="active",
        updated_since=datetime.now() - timedelta(days=30)
    )
    all_intents.extend(intents)

intents = all_intents

# 3. 讀取前次意圖快照（⚠️ 按意圖分別取最新）
# 如果是 group 層級，從主 workspace 讀取（或支持 group 層級 snapshot）
primary_workspace_id = workspace_ids[0] if workspace_ids else workspace_id
# ⚠️ get_latest 是同步方法（不是 async）
snapshot_map = {}
for intent in intents:
    snapshot = artifact_store.get_latest(
        workspace_id=primary_workspace_id,  # 使用主 workspace
        artifact_type=ArtifactType.INTENT_SNAPSHOT,
        filter={"content.intent_id": intent.id},
        order_by="-created_at"
    )
    if snapshot and snapshot.content:
        snapshot_map[intent.id] = snapshot  # 存整個 artifact，不只 content

# 3. 計算 intent_drift（語意漂移）
# ⚠️ 統一用相同欄位：title + description + questions + tags
def intent_to_text(intent: IntentCard) -> str:
    """將意圖轉成用於 embedding 的文本"""
    questions = intent.metadata.get("questions", [])
    questions_text = " ".join(questions) if questions else ""
    # ⚠️ intent.tags 是 List[str]，直接用
    tags_text = " ".join(intent.tags)
    storyline_text = " ".join(intent.storyline_tags)
    return f"{intent.title} {intent.description} {questions_text} {tags_text} {storyline_text}"

for intent in intents:
    prev_snapshot_artifact = snapshot_map.get(intent.id)
    if prev_snapshot_artifact:
        # ⚠️ 從 snapshot.content 讀取，不是 snapshot.title 等
        prev_content = prev_snapshot_artifact.content
        prev_text = " ".join([
            prev_content.get("title", ""),
            prev_content.get("description", ""),
            " ".join(prev_content.get("questions", [])),
            " ".join(prev_content.get("tags", [])),
            " ".join(prev_content.get("storyline_tags", []))
        ])

        current_text = intent_to_text(intent)

        current_vec = await embedding_service.embed(current_text)
        previous_vec = await embedding_service.embed(prev_text)

        drift_value = 1 - cosine_similarity([current_vec], [previous_vec])[0][0]
        intent.metadata["drift"] = drift_value
        # ⚠️ 保存快照 artifact id（不是 intent_id），用於溯源
        intent.metadata["previous_snapshot_id"] = prev_snapshot_artifact.id
    else:
        intent.metadata["drift"] = 0.5  # 新意圖給中等漂移
        intent.metadata["previous_snapshot_id"] = None

# 4. 計算 intent_density（聚類密集度）
# ⚠️ 統一用相同欄位（含 questions + tags）+ L2 normalize + HDBSCAN
texts = [intent_to_text(i) for i in intents]
vectors = await embedding_service.embed_batch(texts)
vectors = normalize(np.array(vectors), norm='l2')

clusterer = hdbscan.HDBSCAN(min_cluster_size=2, metric='euclidean')
cluster_labels = clusterer.fit_predict(vectors)

for idx, (intent, label) in enumerate(zip(intents, cluster_labels)):
    if label == -1:
        intent.metadata["density"] = 0.0
    else:
        cluster_indices = [i for i, l in enumerate(cluster_labels) if l == label and i != idx]
        if cluster_indices:
            cluster_vecs = [vectors[i] for i in cluster_indices]
            avg_sim = np.mean([cosine_similarity([vectors[idx]], [cv])[0][0] for cv in cluster_vecs])
            cluster_size = len(cluster_indices) + 1
            # ⚠️ 乘法，不是除法
            intent.metadata["density"] = cluster_size * avg_sim
        else:
            intent.metadata["density"] = 0.0

# 5. 決定搜集策略
# ⚠️ 使用完整 mode_triggers 結構
def determine_mode(intents: List[IntentCard], research_config: Dict) -> Tuple[str, Dict]:
    """根據 drift/density 決定模式，並返回觸發原因"""
    mode_triggers = research_config.get("mode_triggers", {
        "broaden": {
            "drift_threshold": 0.35,
            "min_intents": 2
        },
        "narrow": {
            "density_threshold": 4.0,
            "min_intents": 2
        }
    })

    broaden_cfg = mode_triggers.get("broaden", {})
    narrow_cfg = mode_triggers.get("narrow", {})

    high_drift_intents = [
        i for i in intents
        if i.metadata.get("drift", 0) > broaden_cfg.get("drift_threshold", 0.35)
    ]
    high_density_intents = [
        i for i in intents
        if i.metadata.get("density", 0) > narrow_cfg.get("density_threshold", 4.0)
    ]

    trigger_info = {
        "high_drift_count": len(high_drift_intents),
        "high_density_count": len(high_density_intents),
        "high_drift_intents": [i.id for i in high_drift_intents],
        "high_density_intents": [i.id for i in high_density_intents]
    }

    if len(high_drift_intents) >= broaden_cfg.get("min_intents", 2):
        return "broaden", trigger_info
    elif len(high_density_intents) >= narrow_cfg.get("min_intents", 2):
        return "narrow", trigger_info
    else:
        return "steady", trigger_info

mode, trigger_info = determine_mode(intents, workspace.metadata.get("research_config", {}))

# 6. 更新 research_config（完整結構）
research_config = {
    "mode": mode,
    "last_sync_at": datetime.now().isoformat(),
    "mode_triggers": {
        "broaden": {
            "drift_threshold": 0.35,
            "min_intents": 2
        },
        "narrow": {
            "density_threshold": 4.0,
            "min_intents": 2
        }
    },
    "trigger_info": trigger_info,
    "weekly_budget": {
        "max_materials": 30,
        "min_contrarian_per_intent": 2
    },
    "query_policy": {
        "freshness_days": 14,
        "dedup_similarity_threshold": 0.85
    }
}
workspace.metadata["research_config"] = research_config

# 8. 創建意圖快照（供下次 drift 計算）
# ⚠️ 使用 primary_workspace_id（如果是 group 層級，使用主 workspace）
primary_workspace_id = workspace_ids[0] if workspace_ids else workspace_id

for intent in intents:
    snapshot = Artifact(
        workspace_id=primary_workspace_id,  # 使用主 workspace
        artifact_type=ArtifactType.INTENT_SNAPSHOT,
        title=f"Snapshot: {intent.title}",
        content={
            "intent_id": intent.id,
            "workspace_id": intent.workspace_id if hasattr(intent, 'workspace_id') else primary_workspace_id,
            "group_id": group_id if group_id else None,  # Group 層級標記
            "workspace_ids": workspace_ids if len(workspace_ids) > 1 else None,  # 多 workspace 標記
            "title": intent.title,
            "description": intent.description,
            # ⚠️ 統一欄位，與 intent_to_text 一致
            "questions": intent.metadata.get("questions", []),
            "tags": intent.tags,  # List[str]，直接存
            "storyline_tags": intent.storyline_tags,
            "drift": intent.metadata.get("drift"),
            "density": intent.metadata.get("density"),
            # ⚠️ 保存前次快照 artifact id（用於溯源）
            "previous_snapshot_id": intent.metadata.get("previous_snapshot_id"),
            "snapshot_at": datetime.now().isoformat()
        }
    )
    await artifact_store.create(snapshot)
```

## 輸出

```yaml
sync_result:
  workspace_id: "ws_001"
  synced_at: "2026-01-01T10:00:00Z"

  # ⚠️ 統一模式名
  mode: "broaden"  # broaden | narrow | steady

  research_config:
    mode_triggers:
      broaden:
        drift_threshold: 0.35
        min_intents: 2
      narrow:
        density_threshold: 4.0
        min_intents: 2
    trigger_info:
      high_drift_count: 2
      high_density_count: 0
      high_drift_intents: ["intent_001", "intent_003"]
      high_density_intents: []
    weekly_budget:
      max_materials: 30
      min_contrarian_per_intent: 2
    query_policy:
      freshness_days: 14
      dedup_similarity_threshold: 0.85

  intents:
    - id: "intent_001"
      title: "搞懂 multi-agent HITL"
      drift: 0.42   # > 0.35 → 高漂移
      density: 1.2  # < 4.0 → 不擁擠

    - id: "intent_002"
      title: "理解 agent 評估指標"
      drift: 0.12   # 穩定
      density: 4.8  # > 4.0 → 擁擠

  recommendations:
    - intent_id: "intent_001"
      action: "開啟探索模式，擴大搜索範圍"
      reason: "drift > 0.35，方向有變動"

    - intent_id: "intent_002"
      action: "考慮合併到相似意圖"
      reason: "density > 4.0，與其他意圖高度重疊"

  # 創建的快照
  snapshots_created: 2

## 策略詳解

### 探索模式 (broaden)
- **觸發條件**：有 2+ 個意圖的 drift > 0.35
- **行為**：
  - 擴大關鍵字範圍
  - 提高來源權重（官方/論文 > 部落格）
  - 增加抓取頻率

### 收斂模式 (narrow)
- **觸發條件**：有 2+ 個意圖的 density > 4.0
- **行為**：
  - 先做意圖去重（建議合併）
  - 縮小關鍵字範圍
  - 增加 contrast 任務（抓反方）

### 穩定模式 (steady)
- **觸發條件**：drift 和 density 都在正常範圍
- **行為**：
  - 維持現有搜集策略
  - 正常頻率抓取

## 依賴

| 服務 | 用途 |
|------|------|
| `IntentDriftService` | 計算 drift/density（使用 HDBSCAN） |
| `EmbeddingService` | text-embedding-3-small 模型 |
| `artifact_store` | 創建 intent_snapshot Artifact |

# Three.js Sandbox 優化實作路徑規劃

## 目標概述

將現有的 Three.js Hero 生成流程優化為基於 **Sandbox 的迭代式改進體驗**，讓用戶可以：
1. 在同一個作品中進行迭代修改（而非每次生成全新的 demo）
2. 通過自然語言指令直接修改現有場景
3. 圈定局部進行精確修改
4. 直觀看到每次變更的過程和效果

## 當前狀態分析

### 現有功能
- ✅ Playbook: `threejs_hero_landing` 可以生成 Three.js 場景
- ✅ 文件落地到 `artifacts/threejs_hero_landing/{execution_id}/` 目錄
- ✅ 使用 `filesystem_write_file` 工具寫入文件
- ✅ 可以生成 React Three Fiber 組件

### 當前限制
- ❌ 每次執行都是全新的 execution_id，沒有版本連續性
- ❌ 無法讀取和修改現有場景
- ❌ 沒有版本管理和 Before/After 對比
- ❌ 無法進行局部修改

## 核心概念：Sandbox

### 定義
**Sandbox** 是一個「被嚴格圈起來的活動空間」：
- 固定目錄結構：`sandboxes/threejs-hero/{slug}/`
- 同一作品的所有版本都在這裡
- 安全邊界：不會影響其他專案
- 可以 local 或 cloud 實現

### 目錄結構設計

```
sandboxes/
└── threejs-hero/
    └── {slug}/                    # 例如: "particle-network-001"
        ├── versions/
        │   ├── v1/
        │   │   ├── index.html     # 獨立版本（可選）
        │   │   ├── Component.tsx  # React 組件版本
        │   │   └── metadata.json  # 版本元數據
        │   ├── v2/
        │   │   └── ...
        │   └── current -> v2      # 當前版本符號鏈接
        ├── preview/               # 預覽相關
        │   └── dev-server/        # 開發服務器配置
        └── sandbox.json           # Sandbox 元數據
```

## 實作路徑

### Phase 1: 建立 Sandbox 基礎架構

#### 1.1 定義 Sandbox 工具集

創建新的工具類：`ThreeJSSandboxTool`

**工具列表：**
- `threejs_sandbox.create_scene(slug, initial_prompt, workspace_id)` - 創建新的 sandbox 和 v1
- `threejs_sandbox.read_scene(slug, version=None)` - 讀取指定版本的場景代碼
- `threejs_sandbox.update_scene(slug, modification_prompt, target_version=None)` - 基於現有版本進行修改
- `threejs_sandbox.list_versions(slug)` - 列出所有版本
- `threejs_sandbox.get_version_diff(slug, version1, version2)` - 獲取版本差異
- `threejs_sandbox.set_current_version(slug, version)` - 設置當前版本

**文件位置：**
```
mindscape-ai-local-core/backend/app/services/tools/threejs_sandbox/
├── __init__.py
├── threejs_sandbox_tools.py      # 工具實現
├── sandbox_manager.py            # Sandbox 管理器
└── version_manager.py            # 版本管理器
```

#### 1.2 Sandbox 管理器實現

**功能：**
- 管理 sandbox 目錄結構
- 處理 slug 生成和驗證
- 維護 sandbox 元數據
- 處理版本符號鏈接

**元數據結構：**
```json
{
  "sandbox_id": "threejs-hero/particle-network-001",
  "slug": "particle-network-001",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z",
  "workspace_id": "...",
  "current_version": "v2",
  "versions": ["v1", "v2"],
  "tags": ["particles", "interactive"]
}
```

#### 1.3 版本管理器實現

**功能：**
- 創建新版本
- 複製上一版本的內容
- 生成版本差異
- 維護版本元數據

**版本元數據結構：**
```json
{
  "version": "v2",
  "created_at": "2024-01-01T00:00:00Z",
  "modification_prompt": "粒子密度減半但保留現在顏色",
  "files": {
    "Component.tsx": {
      "path": "versions/v2/Component.tsx",
      "size": 12345,
      "checksum": "abc123..."
    }
  },
  "change_summary": {
    "type": "modification",
    "changes": [
      "粒子數量從 300 減少為 150",
      "線條透明度略降低",
      "主標題位置略往上移 20px"
    ]
  }
}
```

### Phase 2: 實現迭代式改進

#### 2.1 修改 Playbook 流程

**新的 Playbook 流程：**

1. **首次創建**（保持現有流程）
   - 用戶輸入需求
   - 生成 v1 場景
   - 創建 sandbox
   - 啟動預覽

2. **迭代修改**（新流程）
   - 用戶說：「粒子密度減半但保留現在顏色」
   - AI 使用 `read_scene(slug, version="current")` 讀取當前版本
   - AI 分析代碼，生成 patch
   - AI 使用 `update_scene(slug, modification_prompt, target_version="v2")` 應用修改
   - 自動生成變更摘要
   - 預覽自動刷新

#### 2.2 實現 update_scene 邏輯

**核心邏輯：**
```python
async def update_scene(
    slug: str,
    modification_prompt: str,
    target_version: Optional[str] = None
):
    # 1. 讀取當前版本
    current_version = get_current_version(slug)
    current_files = read_version_files(slug, current_version)

    # 2. 生成新版本號
    new_version = get_next_version(slug)

    # 3. 讓 LLM 分析並生成 patch
    patch = await generate_code_patch(
        current_files,
        modification_prompt
    )

    # 4. 應用 patch
    new_files = apply_patch(current_files, patch)

    # 5. 寫入新版本
    write_version_files(slug, new_version, new_files)

    # 6. 生成變更摘要
    change_summary = await generate_change_summary(
        current_files,
        new_files,
        modification_prompt
    )

    # 7. 更新 metadata
    update_version_metadata(slug, new_version, {
        "modification_prompt": modification_prompt,
        "change_summary": change_summary
    })

    # 8. 設置為當前版本
    set_current_version(slug, new_version)

    return {
        "sandbox_id": f"threejs-hero/{slug}",
        "new_version": new_version,
        "change_summary": change_summary,
        "preview_url": get_preview_url(slug, new_version)
    }
```

### Phase 3: 實現局部修改功能

#### 3.1 代碼層級的圈定

**工具擴展：**
- `threejs_sandbox.update_scene_with_selection(slug, file_path, selection_range, modification_prompt)`

**實現方式：**
1. 用戶在 UI 中選擇代碼塊（提供行號範圍）
2. 提取選中的代碼片段
3. 將「選中代碼 + 修改指令」發送給 LLM
4. LLM 只生成針對該片段的 patch
5. 應用 patch 到指定位置

**選擇格式：**
```json
{
  "file_path": "Component.tsx",
  "selection": {
    "start_line": 45,
    "end_line": 67,
    "code_snippet": "const particleCount = 300; // ..."
  },
  "modification_prompt": "讓密度少一點，但保持現在動態感，別動顏色"
}
```

#### 3.2 視覺層級的圈定（進階）

**實現思路：**
1. 在 preview 中實現框選功能
2. 將視覺座標映射到代碼範圍
3. 分析哪些參數影響選中區域
4. 只修改相關參數

**技術要點：**
- 使用 Three.js Raycasting 將螢幕座標轉換為 3D 物件
- 分析物件對應的代碼結構
- 生成針對性的修改指令

**第一階段可以先實現：**
- 文本描述式的圈定（「右上角的粒子群」）
- 由 AI 分析並推斷對應的代碼範圍

### Phase 4: 實現變更可視化

#### 4.1 Before/After 切換

**UI 組件設計：**
```
┌─────────────────────────────────────────┐
│  Three.js Hero Editor                   │
├─────────────────────────────────────────┤
│  [v1] [v2] [v3] [v4]  ← 版本時間線      │
│                                         │
│  ┌─────────────┐  ┌─────────────┐      │
│  │  Before     │  │  After      │      │
│  │  (v2)       │  │  (v4)       │      │
│  │             │  │             │      │
│  │  [Preview]  │  │  [Preview]  │      │
│  └─────────────┘  └─────────────┘      │
│                                         │
│  變更摘要：                              │
│  ✅ 粒子數量從 300 減少為 150            │
│  ✅ 線條透明度略降低                     │
│  ✅ 主標題位置略往上移 20px              │
└─────────────────────────────────────────┘
```

**API 支持：**
- `threejs_sandbox.get_version_preview_url(slug, version)` - 獲取版本預覽 URL
- `threejs_sandbox.compare_versions(slug, version1, version2)` - 對比兩個版本

#### 4.2 變更摘要生成

**實現方式：**
每次 `update_scene` 後，讓 AI 自動生成變更摘要：

```python
async def generate_change_summary(
    old_files: Dict[str, str],
    new_files: Dict[str, str],
    modification_prompt: str
) -> Dict[str, Any]:
    # 使用 LLM 分析代碼差異
    diff = compute_diff(old_files, new_files)

    summary_prompt = f"""
    用戶的修改指令：{modification_prompt}

    代碼變更：
    {diff}

    請用簡潔的中文列出這次修改做了什麼：
    1. 格式：✅ [具體變更描述]
    2. 每個變更一行
    3. 只列出用戶可見或有意義的變更
    """

    summary = await llm_call(summary_prompt)
    return {
        "type": "modification",
        "prompt": modification_prompt,
        "changes": parse_summary(summary),
        "diff": diff
    }
```

### Phase 5: 更新 Playbook

#### 5.1 修改 `threejs_hero_landing` Playbook

**新增階段：**

```markdown
### Phase 7: Sandbox 迭代模式

#### 步驟 7.1: 創建 Sandbox（首次執行）
- 使用 `threejs_sandbox.create_scene()` 創建新 sandbox
- 生成 v1 場景
- 啟動預覽服務器

#### 步驟 7.2: 迭代改進（後續對話）
- 檢測是否已有 sandbox（通過 slug 或上下文）
- 如果有，使用 `threejs_sandbox.read_scene()` 讀取當前版本
- 使用 `threejs_sandbox.update_scene()` 進行修改
- 自動生成變更摘要
- 提供 Before/After 對比連結

#### 步驟 7.3: 局部修改（可選）
- 如果用戶選擇了代碼片段，使用 `threejs_sandbox.update_scene_with_selection()`
- 如果用戶圈選了視覺區域，分析並映射到代碼範圍
```

#### 5.2 新增 Playbook: `threejs_sandbox_iteration`

專門用於迭代修改的輕量級 Playbook：

```markdown
playbook_code: threejs_sandbox_iteration
name: Three.js Sandbox 迭代修改
description: 在現有 Three.js hero 場景上進行迭代式改進

## 流程

1. 檢測現有 sandbox（通過 slug 或 workspace 上下文）
2. 讀取當前版本代碼
3. 理解用戶的修改指令
4. 生成並應用 patch
5. 生成變更摘要
6. 更新預覽
```

### Phase 6: UI 整合（未來）

#### 6.1 版本時間線組件

**功能：**
- 顯示所有版本
- 點擊版本切換預覽
- 並排對比兩個版本

#### 6.2 代碼編輯器整合

**功能：**
- 顯示當前版本的代碼
- 支持選擇代碼塊
- 右鍵菜單：「只改這一段」

#### 6.3 預覽整合

**功能：**
- 實時預覽當前版本
- 支持框選視覺區域
- Before/After 分屏對比

## 技術實作細節

### 6.1 文件結構

```
mindscape-ai-local-core/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── tools/
│   │   │   │   └── threejs_sandbox/
│   │   │   │       ├── __init__.py
│   │   │   │       ├── threejs_sandbox_tools.py
│   │   │   │       ├── sandbox_manager.py
│   │   │   │       └── version_manager.py
│   │   │   └── ...
│   │   └── ...
│   └── i18n/
│       └── playbooks/
│           └── zh-TW/
│               ├── threejs_hero_landing.md (更新)
│               └── threejs_sandbox_iteration.md (新增)
└── data/
    └── sandboxes/
        └── threejs-hero/
            └── {slug}/
```

### 6.2 工具註冊

在 `workspace-pack.yaml` 或創建新的 `threejs-sandbox-pack.yaml`：

```yaml
name: threejs-sandbox-pack
tools:
  - name: threejs_sandbox.create_scene
    type: threejs_sandbox
    scope: workspace
  - name: threejs_sandbox.read_scene
    type: threejs_sandbox
    scope: workspace
  - name: threejs_sandbox.update_scene
    type: threejs_sandbox
    scope: workspace
  # ... 其他工具
```

### 6.3 Sandbox 路徑配置

**配置位置：**
```python
# backend/app/config/sandbox_config.py

SANDBOX_BASE_PATH = Path("data/sandboxes")
THREEJS_SANDBOX_PATH = SANDBOX_BASE_PATH / "threejs-hero"
DEV_SERVER_PORT_RANGE = (8888, 8899)  # 每個 sandbox 使用不同端口
```

### 6.4 預覽服務器管理

**實現方式：**
- 每個 sandbox 可以有自己的預覽服務器
- 使用端口池管理（避免衝突）
- 支持熱重載（文件變更自動刷新）

**簡單實現：**
```python
class SandboxPreviewServer:
    def __init__(self, sandbox_path: Path, port: int):
        self.sandbox_path = sandbox_path
        self.port = port
        self.server_process = None

    def start(self):
        # 使用簡單 HTTP 服務器或專用 Three.js 預覽工具
        pass

    def stop(self):
        # 停止服務器
        pass

    def get_preview_url(self, version: str) -> str:
        return f"http://localhost:{self.port}/versions/{version}/index.html"
```

## 實作優先級

### 第一階段（核心功能）
1. ✅ 建立 Sandbox 基礎架構
2. ✅ 實現 `create_scene`, `read_scene`, `update_scene` 工具
3. ✅ 實現版本管理（v1, v2, v3...）
4. ✅ 修改 Playbook 支持迭代模式
5. ✅ 實現變更摘要生成

### 第二階段（增強體驗）
6. ⏳ 實現代碼層級的圈定修改
7. ⏳ 實現 Before/After 對比 API
8. ⏳ 優化預覽服務器（熱重載）

### 第三階段（進階功能）
9. ⏳ 實現視覺層級的圈定
10. ⏳ UI 整合（版本時間線、代碼編輯器）
11. ⏳ Cloud sandbox 支持

## 測試計劃

### 單元測試
- Sandbox 管理器測試
- 版本管理器測試
- 代碼差異計算測試

### 整合測試
- 完整的創建 → 修改 → 對比流程
- 多版本管理測試
- 並發修改測試

### 端到端測試
- 從 Playbook 執行到預覽的完整流程
- 迭代修改的完整體驗

## 遷移計劃

### 現有數據遷移
- 現有的 `artifacts/threejs_hero_landing/{execution_id}/` 可以轉換為 sandbox
- 創建遷移腳本，將現有執行轉為 v1

### 向後兼容
- 保持現有 Playbook 仍可運行
- 新功能作為可選項逐步引入

## 未來擴展

### Cloud Sandbox
- 支持雲端存儲
- 可分享的預覽連結
- 協作編輯

### 更多 Sandbox 類型
- 書稿 sandbox
- 影片腳本 sandbox
- 網站設計 sandbox

## 參考資源

- 現有 Playbook: `threejs_hero_landing.md`
- 文件系統工具: `filesystem_tools.py`
- Artifact 創建器: `playbook_output_artifact_creator.py`


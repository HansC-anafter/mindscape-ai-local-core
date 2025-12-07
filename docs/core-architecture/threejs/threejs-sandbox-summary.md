# Three.js Sandbox 優化實作規劃總結

## 📋 實作路徑總覽

我已經為你規劃了完整的 Three.js Sandbox 優化實作路徑，包含三個核心文檔：

### 1. **總體規劃文檔** ([threejs-sandbox-implementation-plan.md](threejs-sandbox-implementation-plan.md))
   - 完整的概念設計
   - 架構規劃
   - 功能優先級
   - 未來擴展方向

### 2. **詳細步驟文檔** ([threejs-sandbox-implementation-steps.md](threejs-sandbox-implementation-steps.md))
   - 逐步實作指南
   - 工具接口定義
   - 整合檢查清單
   - 測試計劃

### 3. **程式碼範例文檔** ([threejs-sandbox-code-examples.md](threejs-sandbox-code-examples.md))
   - 完整的程式碼範例
   - 可直接使用的模板
   - 使用範例

## 🎯 核心概念

### Sandbox 是什麼？

**Sandbox = 被嚴格圈起來的活動空間**

- ✅ 固定目錄結構：`sandboxes/threejs-hero/{slug}/`
- ✅ 同一作品的所有版本都在這裡
- ✅ 安全邊界：不會影響其他專案
- ✅ 支持 local 和 cloud 兩種模式

### 目錄結構

```
sandboxes/threejs-hero/{slug}/
├── versions/
│   ├── v1/
│   │   ├── Component.tsx
│   │   ├── index.html
│   │   └── metadata.json
│   ├── v2/
│   │   └── ...
│   └── current -> v2
└── sandbox.json
```

## 🚀 核心功能

### 1. 迭代式改進（核心功能）

**體驗流程：**
1. 第一次：創建 `v1` + 開 preview
2. 第二次：說「粒子密度減半」→ AI 讀取 `v1` → 生成 `v2` → preview 刷新
3. 第三次：說「相機拉遠一點」→ AI 讀取 `v2` → 生成 `v3` → preview 刷新

**實現工具：**
- `threejs_sandbox.create_scene(slug, prompt)` - 創建新 sandbox
- `threejs_sandbox.read_scene(slug, version)` - 讀取現有場景
- `threejs_sandbox.update_scene(slug, modification_prompt)` - 基於現有版本修改

### 2. 局部修改（增強功能）

**兩種方式：**

#### A. 代碼層級的圈定
- 用戶選擇代碼塊（行號範圍）
- 右鍵「只改這一段」
- AI 只生成針對該片段的 patch

#### B. 視覺層級的圈定（進階）
- 在 preview 上框選區域
- AI 分析對應的代碼範圍
- 只修改相關參數

### 3. 變更可視化（體驗優化）

**功能：**
- Before/After 切換
- 變更摘要（用自然語言列出修改）
- 版本時間線

**變更摘要範例：**
```
✅ 粒子數量從 300 減少為 150
✅ 線條透明度略降低，避免畫面過亮
✅ 主標題的位置略往上移 20px
```

## 📦 實作階段

### Phase 1: 基礎架構（第一週）

**目標：** 建立可運行的 MVP

1. ✅ 創建 Sandbox 管理器
2. ✅ 創建版本管理器
3. ✅ 實現三個核心工具
4. ✅ 註冊工具到系統
5. ⏳ 整合到 Playbook

### Phase 2: 迭代改進（第二週）

**目標：** 實現完整的迭代體驗

1. ⏳ 實現 `update_scene` 的完整邏輯
2. ⏳ 整合 LLM 生成修改後的代碼
3. ⏳ 實現變更摘要生成
4. ⏳ 測試完整流程

### Phase 3: 增強功能（第三週）

**目標：** 局部修改和可視化

1. ⏳ 實現代碼層級的圈定修改
2. ⏳ 實現 Before/After 對比 API
3. ⏳ 優化預覽服務器

### Phase 4: 進階功能（未來）

1. ⏳ 視覺層級的圈定
2. ⏳ UI 整合
3. ⏳ Cloud sandbox 支持

## 🔧 技術要點

### 工具架構

```
threejs_sandbox/
├── sandbox_manager.py      # Sandbox 管理
├── version_manager.py      # 版本管理
├── threejs_sandbox_tools.py # 工具實現
└── utils.py                # 輔助函數
```

### 核心工具

1. **`threejs_sandbox.create_scene`**
   - 創建新 sandbox
   - 生成 v1 場景
   - 返回 sandbox_id 和 preview_url

2. **`threejs_sandbox.read_scene`**
   - 讀取指定版本的場景代碼
   - 返回所有文件內容和元數據

3. **`threejs_sandbox.update_scene`**
   - 讀取當前版本
   - 生成新版本（基於修改指令）
   - 生成變更摘要
   - 返回新版本信息

### Playbook 整合

**現有 Playbook 更新：**
- `threejs_hero_landing.md` - 添加 Sandbox 模式選項

**新增 Playbook：**
- `threejs_sandbox_iteration.md` - 專門用於迭代修改

## 📝 使用範例

### 創建新 Sandbox

```
用戶：「生成一個動態粒子網絡的 Three.js hero 區塊」

AI:
1. 生成 slug: "particle-network-001"
2. 調用 create_scene("particle-network-001", "...")
3. 生成 v1 場景
4. 返回預覽連結
```

### 迭代修改

```
用戶：「粒子密度減半但保留現在顏色」

AI:
1. 檢測到有 sandbox "particle-network-001"
2. 調用 read_scene("particle-network-001") 讀取 v1
3. 分析代碼，生成修改後的版本
4. 調用 update_scene("particle-network-001", "粒子密度減半...")
5. 生成 v2
6. 返回變更摘要和預覽連結
```

### 局部修改

```
用戶：（選擇了代碼中的粒子配置區塊）
     「讓密度少一點，但保持現在動態感，別動顏色」

AI:
1. 提取選中的代碼片段
2. 只針對該片段生成 patch
3. 應用 patch 到指定位置
4. 生成新版本
```

## 🎨 體驗提升

### 之前 vs 之後

**之前：**
- 每次都是全新的 execution_id
- 無法保留修改歷史
- 無法進行迭代改進
- 體驗：一堆孤立的 demo

**之後：**
- 同一個作品的迭代成長
- 完整的版本歷史
- 自然語言迭代修改
- 變更可視化
- 體驗：作品在「成長」

## 📚 參考文檔

1. **實作規劃**：[Three.js Sandbox 實作規劃](threejs-sandbox-implementation-plan.md)
   - 完整的概念和架構設計

2. **實作步驟**：[Three.js Sandbox 實作步驟](threejs-sandbox-implementation-steps.md)
   - 詳細的實作指南和檢查清單

3. **程式碼範例**：[Three.js Sandbox 程式碼範例](threejs-sandbox-code-examples.md)
   - 可直接使用的程式碼模板

## 🚦 下一步行動

### 立即開始（今天）

1. 創建工具目錄結構
   ```bash
   mkdir -p mindscape-ai-local-core/backend/app/services/tools/threejs_sandbox
   ```

2. 實現 `SandboxManager` 類
   - 參考：[Three.js Sandbox 程式碼範例](threejs-sandbox-code-examples.md)

3. 實現 `VersionManager` 類
   - 參考：[Three.js Sandbox 程式碼範例](threejs-sandbox-code-examples.md)

### 本週目標

1. ✅ 完成三個核心工具的基礎實現
2. ✅ 註冊工具到系統
3. ✅ 測試創建和讀取功能

### 下週目標

1. ⏳ 完成 `update_scene` 的完整實現
2. ⏳ 整合 LLM 生成邏輯
3. ⏳ 實現變更摘要生成
4. ⏳ 更新 Playbook 支持新功能

## 💡 關鍵洞察

### 為什麼需要 Sandbox？

1. **安全邊界**：不會影響其他專案
2. **版本連續性**：同一作品的多個版本
3. **迭代體驗**：可以反覆改進同一個作品
4. **變更追蹤**：完整的修改歷史

### 核心價值

> **有了 sandbox 之後的體驗不是「指令變不一樣」，而是：**
> - 你可以把 AI 當成「固定在這一個作品上工作的人」
> - 可以指定區塊改，也可以只用講的
> - 最重要是：每次改的影響範圍和變更過程都能被看見、被還原

## 🎯 成功標準

### MVP 成功標準

- [ ] 可以創建新的 sandbox
- [ ] 可以讀取場景代碼
- [ ] 可以基於現有版本生成新版本
- [ ] 版本管理正常工作（v1, v2, v3...）
- [ ] 基本變更摘要可以生成

### 完整版本成功標準

- [ ] 完整的迭代修改體驗流暢
- [ ] 變更摘要準確且有用
- [ ] Before/After 對比可以工作
- [ ] 局部修改功能可用
- [ ] UI 整合完成

## 📞 需要幫助？

如果實作過程中遇到問題，可以：

1. 參考程式碼範例文檔
2. 查看詳細步驟文檔
3. 檢查現有工具實現（`filesystem_tools.py`）作為參考

祝實作順利！🎉


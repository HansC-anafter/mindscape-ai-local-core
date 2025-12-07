# Sandbox 系統設計總結

## 🎯 核心洞察

### 關鍵原則

> **凡是「AI 幫你改東西（不是純讀）的場合，都應該經過 sandbox 這一層。**

這不是只有 three.js 才需要，而是**所有 AI 寫入操作**的統一抽象。

## 🏗️ 系統架構

### 三層設計

```
┌─────────────────────────────────────┐
│  UI Layer (統一)                      │
│  - Sandbox Viewer (共用元件)          │
│  - 不同類型的 preview renderer        │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  Tool Layer                          │
│  - sandbox.threejs.*                 │
│  - sandbox.writing.*                 │
│  - sandbox.project.*                 │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  SandboxManager (系統級)              │
│  - 統一版本管理                       │
│  - 統一 diff 和摘要                   │
│  - 統一存儲抽象                       │
└─────────────────────────────────────┘
```

## 📦 Sandbox 類型

### 1. Three.js Hero (`threejs_hero`)

**特點：**
- 視覺 + code 混合
- 需要 preview 和視覺圈選
- 結構：`versions/v1/Component.tsx`, `index.html`

**工具：**
- `sandbox.threejs.create_scene`
- `sandbox.threejs.read_scene`
- `sandbox.threejs.apply_patch`

### 2. Writing Project (`writing_project`)

**特點：**
- 純文字內容
- 結構化章節
- 結構：`outline.md`, `ch01.md`, `ch02.md`, `meta.json`

**工具：**
- `sandbox.writing.create_project`
- `sandbox.writing.create_chapter`
- `sandbox.writing.read_section`
- `sandbox.writing.apply_patch`

### 3. Project Repo (`project_repo`)

**特點：**
- 可以是 patch 集合或專用 git branch
- 需要 merge 機制
- 結構：`patches/`, `branch/`, 或 `sandbox/` 目錄

**工具：**
- `sandbox.project.plan_patch`
- `sandbox.project.apply_patch`
- `sandbox.project.merge_to_main`（需要用戶確認）

## ✨ 統一能力

### 1. 統一版本管理

所有 sandbox 類型共享：
- 版本號格式：v1, v2, v3...
- 版本元數據格式
- 版本列表和切換

### 2. 統一局部修改

所有 sandbox 類型都支持：
- **文字檔** → 選取範圍當 patch scope
- **Code** → `start_line / end_line` + diff
- **Three.js** → 視覺圈選 + mapping 到 config

### 3. 統一變更可視化

所有 sandbox 類型共享：
- 版本時間線
- Before/After 對比
- AI 口語摘要

**範例：**
```
書稿 v3：增加了 XX 小節，刪掉了 YY 段
Three.js v2：粒子變少、顏色變紫
Repo v5：新增兩個 function，刪掉一個 unused import
```

## 🔄 遷移策略

### 現狀 → 新架構

**舊方式：**
```python
await filesystem_write_file(
    file_path="artifacts/threejs_hero_landing/{execution_id}/Component.tsx",
    content=generated_code
)
```

**新方式：**
```python
sandbox_id = await sandbox.create_sandbox(
    sandbox_type="threejs_hero",
    context={"slug": "particle-network-001"},
    workspace_id=workspace_id
)

await sandbox.write_file(
    sandbox_id=sandbox_id,
    file_path="Component.tsx",
    content=generated_code
)
```

### 遷移優先級

1. **Phase 1**：實現系統級 SandboxManager
2. **Phase 2**：遷移 `threejs_hero_landing` Playbook
3. **Phase 3**：遷移 `yearly_personal_book` Playbook
4. **Phase 4**：遷移其他相關 Playbook

## 🎨 統一 UI 模式

### Sandbox Viewer 共用元件

所有 sandbox 類型共享相同的 UI 結構：

```
┌─────────────────────────────────────┐
│  [預覽] [原始碼] [變更歷史] [AI 對話] │
├─────────────────────────────────────┤
│  預覽區域（根據 sandbox_type 渲染）   │
├─────────────────────────────────────┤
│  版本時間線                          │
│  [v1] [v2] [v3] [v4]                │
│                                      │
│  變更摘要：                          │
│  ✅ 粒子數量從 300 減少為 150        │
│  ✅ 線條透明度略降低                  │
└─────────────────────────────────────┘
```

### Preview Renderer

根據 `sandbox_type` 選擇對應的 renderer：
- `threejs_hero` → Three.js 預覽
- `writing_project` → Markdown 渲染
- `project_repo` → Code diff

## 💡 設計價值

### 1. 安全邊界清楚

- 一看 `sandbox_id` 就知道：「這個改動只影響這一小塊世界」
- 不會影響其他專案或系統文件

### 2. 統一機制

- 不用每一種 artefact 都再設計一套版本系統
- 統一的 diff、摘要、回滾機制

### 3. Local / Cloud 一致

- Local：檔案系統
- Cloud：Volume / Bucket
- 對 Playbook / Tool 來說都是 `sandbox.*` 介面

### 4. 擴展性

- 容易添加新的 sandbox 類型
- 統一的接口和 UI 模式

## 📋 實作檢查清單

### 系統級基礎
- [ ] 實現 `SandboxManager` 核心類
- [ ] 實現 `Sandbox` 基類
- [ ] 實現統一版本管理
- [ ] 實現存儲抽象（Local / Cloud）

### 具體類型
- [ ] 實現 `ThreeJSHeroSandbox`
- [ ] 實現 `WritingProjectSandbox`
- [ ] 實現 `ProjectRepoSandbox`

### 工具層
- [ ] 創建 `SandboxToolBase`
- [ ] 實現各類型的工具
- [ ] 註冊工具到系統

### 遷移
- [ ] 遷移 `threejs_hero_landing` Playbook
- [ ] 遷移 `yearly_personal_book` Playbook
- [ ] 更新其他相關 Playbook

### UI
- [ ] 實現 `SandboxViewer` 共用元件
- [ ] 實現不同類型的 preview renderer
- [ ] 實現統一的變更可視化

## 🚀 下一步

1. **閱讀系統架構文檔**：[Sandbox 系統架構設計](sandbox-system-architecture.md)
2. **查看實作步驟**：[Sandbox 系統實作步驟](sandbox-system-implementation-steps.md)
3. **開始實作**：從 `SandboxManager` 核心類開始

## 📚 相關文檔

- [Sandbox 系統架構設計](sandbox-system-architecture.md)
- [Sandbox 系統實作步驟](sandbox-system-implementation-steps.md)
- [Project + Flow 架構設計](../project-flow/project-flow-architecture.md)
- [Three.js Sandbox 實作規劃](../threejs/threejs-sandbox-implementation-plan.md)
- [Three.js Sandbox 程式碼範例](../threejs/threejs-sandbox-code-examples.md)

---

**關鍵洞察：** Sandbox 不是某個特定場景的專屬功能，而是**所有 AI 寫入操作的統一抽象層**。這樣設計可以讓整個系統更安全、更一致、更容易擴展。


# 核心架構文檔

這個目錄包含 Mindscape AI 的核心架構設計文檔，包括：

## 📁 目錄結構

### 🎯 [Sandbox 系統](./sandbox/)
系統級的 Sandbox 架構設計，統一所有 AI 寫入操作。

- [Sandbox 系統架構設計](./sandbox/sandbox-system-architecture.md)
- [Sandbox 系統實作步驟](./sandbox/sandbox-system-implementation-steps.md)
- [Sandbox 系統設計總結](./sandbox/sandbox-system-summary.md)

### 🏗️ [Project + Flow](./project-flow/)
Project 和 Playbook Flow 架構設計，讓多個 playbook 協作完成一個作品。

- [Project + Flow 架構設計](./project-flow/project-flow-architecture.md)
- [Project + Flow 實作步驟](./project-flow/project-flow-implementation-steps.md)
- [Project + Flow 設計總結](./project-flow/project-flow-summary.md)

### 🎯 [Project-First Protocol](./project-first-protocol.md) ⭐ 核心世界觀
專案優先協議：在長期 Workspace 中，偵測對話是否需要建立 Project。

- [Project-First Protocol 設計](./project-first-protocol.md)

### 🏢 [Workspace 生命週期管理](./workspace-lifecycle-management.md) ⭐⭐ 重要修正
Workspace 長期管理、分層記憶、Project PM 指派、人事流動處理。

- [Workspace 生命週期管理](./workspace-lifecycle-management.md)

### 🎨 [Three.js Sandbox](./threejs/)
Three.js Hero 場景的 Sandbox 實作規劃和範例。

- [Three.js Sandbox 索引](./threejs/threejs-sandbox-index.md)
- [Three.js Sandbox 實作規劃](./threejs/threejs-sandbox-implementation-plan.md)
- [Three.js Sandbox 實作步驟](./threejs/threejs-sandbox-implementation-steps.md)
- [Three.js Sandbox 程式碼範例](./threejs/threejs-sandbox-code-examples.md)
- [Three.js Sandbox 快速開始](./threejs/threejs-sandbox-quick-start.md)
- [Three.js Sandbox 規劃總結](./threejs/threejs-sandbox-summary.md)

### 🔍 [OpenSEO 驗證案例](./openseo-validation-case.md) ⭐ 驗證方向
用 OpenSEO 完整工作流驗證 Project + Flow + Sandbox 架構是否正確。

- [OpenSEO 驗證案例](./openseo-validation-case.md)

### ⚠️ [風險檢查與應對清單](./risk-mitigation-checklist.md) ⚠️ **必讀**
檢查 Project + Flow + Sandbox 架構實作中可能踩的坑，並提供應對方案。

- [風險檢查與應對清單](./risk-mitigation-checklist.md)

## 🎯 核心概念

### Project-First Protocol（核心世界觀）⭐

**差異化：**
> 別人是「很多 AI 工具散落在 workspace 裡」；
> 你是「作品級 Project → 有 sandbox 的實體世界 → 上面跑 Flow / 多個 playbook 分工」。

**三個關鍵字：**
1. **Project = 作品宇宙**：所有 artefact 都掛在同一顆 project tree 上
2. **Sandbox = artefact 的真實世界**：每個 playbook 讀/寫的都是「同一個世界」的檔案
3. **Flow = playbook 群組有先後關係**：在同一工地分工，不是各自開新世界

**價值：**
- 一進場就以「專案心態」工作，不是 freestyle
- 統一的世界觀和執行順序
- 清晰的 Workspace 結構

### Sandbox 系統

**原則：凡是「AI 寫入」，一律走 sandbox 流**

- ✅ LLM 可以隨便讀檔（有權限的情況下）
- ❌ 但只要要寫 / 改檔，就必須透過 sandbox tool，不准直接寫實體檔案

**價值：**
- 安全邊界清楚
- 統一版本 / diff / 回滾機制
- local / cloud 一致

### Project + Flow

**解決問題：從「各自做夢」到「一起蓋房子」**

- **Project**：作品級容器，所有檔案、sandbox、playbook 執行都掛在這個 project 底下
- **Playbook Flow**：定義節點和依賴關係，確保執行順序
- **Shared Sandbox**：作品級的檔案世界，所有 playbook 共享同一個 sandbox

**價值：**
- 有「共同世界」（同一份 spec/檔案）
- 有「先後關係」（執行引擎 enforce 順序）
- 有「作品級別」的容器

## 📚 閱讀建議

### 快速了解
1. [Workspace 生命週期管理](./workspace-lifecycle-management.md) ⭐⭐ **重要修正**
2. [Project-First Protocol](./project-first-protocol.md) ⭐ **核心世界觀**
3. [OpenSEO 驗證案例](./openseo-validation-case.md) ⭐ **驗證方向**
4. [Sandbox 系統設計總結](./sandbox/sandbox-system-summary.md)
5. [Project + Flow 設計總結](./project-flow/project-flow-summary.md)

### 深入了解
1. [Sandbox 系統架構設計](./sandbox/sandbox-system-architecture.md)
2. [Project + Flow 架構設計](./project-flow/project-flow-architecture.md)

### 開始實作
1. [實作路徑總覽](./implementation-roadmap.md) ⭐ **對應當前落地現況**
2. [實作路徑詳細對應](./implementation-roadmap-detailed.md) ⭐ **具體文件位置**
3. [OpenSEO 驗證案例](./openseo-validation-case.md) ⭐ **驗證方向**
4. [Sandbox 系統實作步驟](./sandbox/sandbox-system-implementation-steps.md)
5. [Project + Flow 實作步驟](./project-flow/project-flow-implementation-steps.md)
6. [Three.js Sandbox 快速開始](./threejs/threejs-sandbox-quick-start.md)

## 🔗 架構關係

```
Workspace (長期房間，幾年都在這裡)
    ↓
大廳對話 (大家隨便聊、發散、靈感)
    ↓
Project 偵測器 (偵測是否有 project 潛質)
    ↓
建立 Project (掛在同一個 workspace)
    ↓
Project-Assignment Agent (建議 PM)
    ↓
Project (作品容器，有自己的生命週期)
    ↓
Playbook Flow (執行流程)
    ↓
Shared Sandbox (檔案世界)
    ↓
SandboxManager (系統級)
```

## 💡 核心修正

### 新的世界觀

❌ 「每個 project 都去開一個 workspace」

✅ 「大家一直在同一房間聊，過程中長出一堆 project，project 自己有身份和生命週期。」

### 兩個工程炸彈的解決方案

1. **長壽命 workspace 裡的 project 管理**
   - 分層記憶：workspace core / member / project / thread
   - Project Index：只存 metadata，不爆炸
   - 層級化摘要：只壓縮 thread，不亂捏上面三層

2. **Project PM 指派與人事流動**
   - Project-Assignment Agent：自動建議 PM
   - Member Profile Memory：保留歷史記錄
   - Project 轉移機制：處理人事流動

## 🚀 實作狀態

### ✅ 已完成（2025-12-08）

#### Phase 1: 基礎模型層 ✅
- ✅ Project, ArtifactRegistry, PlaybookFlow 模型
- ✅ 資料庫遷移（projects, artifact_registry, playbook_flows）
- ✅ ProjectsStore, PlaybookFlowsStore

#### Phase 2: 服務層 ✅
- ✅ ProjectManager, ProjectDetector, ProjectAssignmentAgent
- ✅ ArtifactRegistryService

#### Phase 3: Orchestrator 整合 ✅
- ✅ ConversationOrchestrator Project 偵測
- ✅ PlaybookRunner Project 模式支持

#### Phase 4: 記憶分層 ✅
- ✅ WorkspaceCoreMemoryService
- ✅ ProjectMemoryService
- ✅ MemberProfileMemoryService
- ✅ ContextBuilder 整合

#### Phase 5: Flow 執行引擎 ✅
- ✅ FlowExecutor（節點調度、依賴解析、重試）
- ✅ ProjectSandboxManager（workspace 隔離）
- ✅ Flow 執行和管理 API
- ✅ Checkpoint 機制
- ✅ Artifact 自動註冊

### 📋 架構演進記錄

- [版本迭代說明](./version-iteration.md) - v2.0 架構變更說明
- [實作路徑總覽](./implementation-roadmap.md) - 實作路徑對應現況
- [實作路徑詳細對應](./implementation-roadmap-detailed.md) - 具體文件位置

> **注意**：詳細的實作進度、驗證結果等內部工作文檔已移至 `docs-internal/core-architecture/` 目錄。

### ⏸️ 後續工作

1. **Playbook 向後兼容適配器**（可選）
2. **UI/UX 升級**（根據設計文檔）
3. **端到端測試與性能優化**


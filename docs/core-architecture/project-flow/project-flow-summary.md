# Project + Playbook Flow 設計總結

## 🎯 核心洞察

### 問題本質

> **現在是「一群 playbook 在各自做夢」，不是「一起蓋同一棟房子」。**

### 三個痛點

1. **沒有「共同世界」**
   - 每個 playbook 各自憑輸入想像，沒有一份「唯一真實版本」的 spec/檔案

2. **沒有「先後關係」**
   - 一堆 playbook 同時被意圖打開、各自跑
   - LLM 在腦內排順序，但執行引擎沒有真的 enforce

3. **沒有「作品級別」的容器**
   - workspace 裡混了各種產物
   - 其實要的是：「這些東西是同一個『作品』底下的部件」

### 解決方案

引入三個一級概念：
1. **Project / Work Unit** - 作品級容器
2. **Playbook Flow** - Playbook 群組/pipeline
3. **Shared Sandbox** - 作品級的檔案世界

## 🏗️ 架構總覽

### 三層設計

```
Intent Layer
    ↓
Orchestrator
    ↓
Project (作品容器)
    ↓
Playbook Flow (執行流程)
    ↓
Shared Sandbox (檔案世界)
```

### 核心概念

#### 1. Project（作品 / 工地）

每次用戶說「幫我做一個關於 xxx 的網頁」，系統先建立一個 Project，所有後續檔案、sandbox、playbook 執行都掛在這個 project 底下。

**結構：**
```python
Project:
  id: web_page_2025xxxx
  type: web_page
  title: "關於 xxx 的網頁"
  workspace_id: current_workspace_id
  flow_id: web_page_flow
  state: active
```

#### 2. Playbook Flow（Playbook 群組）

不是一堆 playbook 平行亂跑，而是定義節點和邊，執行單位是「這個 Project 正在跑 web_page_flow，現在在 A 節點」。

**範例：**
```yaml
nodes:
  A: page_outline_md
  B: hero_threejs
  C: sections_react

edges:
  A -> B (B 要吃 A 的 md_spec)
  A -> C (C 也吃 A 的 md_spec)
```

#### 3. Shared Sandbox（作品級的檔案世界）

對這個 Project 開一個專屬 sandbox，所有 playbook 都寫進同一個 project sandbox，檔案共享機制自然存在。

**結構：**
```
sandboxes/web_page/{project_id}/
  spec/page.md          # A 產出
  hero/index.html       # B 產出
  sections/App.tsx      # C 產出
```

## 🔄 執行流程範例

### 「幫我做一個關於『城市覺知』的網頁」

#### Step 0: Intent 判定
```
用戶：「幫我做一個關於『城市覺知』的網頁」
→ Intent: web_page_project
→ Orchestrator 建立 Project + 掛上 web_page_flow
```

#### Step 1: 節點 A - Page Outline
- Playbook A 產出 `spec/page.md`
- 註冊 artifact: `page_md`
- Flow 知道 A 完成了，才會排 B/C

#### Step 2: 節點 B & C - Hero + Sections
- B 和 C 都讀取 `page_md`（同一份 spec）
- B 產出 `hero/index.html`
- C 產出 `sections/App.tsx`
- 可以平行執行（因為都只依賴 A）

#### Step 3: Workspace UI
```
🧱 Web Page Project – 城市覺知
流程：Outline → Hero → Sections
現況：Hero 已完成草稿、Sections 50%
```

## 🎯 關鍵價值

### 從「各自做夢」到「一起蓋房子」

**之前：**
- 一堆 playbook 平行亂跑
- 各自憑輸入想像，沒有共同世界
- 沒有執行順序保證

**之後：**
- 同一個 Project + Sandbox
- 看同一張藍圖（page.md）
- 各做各工種，但共用同一組 artifact
- 真正的「多工 agent」分工

### 多工 Agent 的真正分工

> 「一群人各自拿到關鍵字瞎忙」
> ↓
> 「在同一個工地、看同一張藍圖、各做各工種，但共用同一組 artefact」

## 🔀 跨 Workspace 支持

### Project 移交

- Project 有 `home_workspace_id`
- 可以在 UI 上選擇：「把這個 Project 拆出去，掛到『Web Design Workspace』」
- 原 workspace 只留下「成果卡」和「shortcut」

**好處：**
- 總控 workspace 不會被各種產物塞爆
- 各專門 workspace 都有自己的 Project 清單

## 📋 實作優先級

### Phase 1: Project 基礎層
1. ✅ 定義 Project 資料結構
2. ✅ 實現 ProjectManager
3. ✅ 實現 ArtifactRegistry
4. ✅ 實現 ProjectSandboxManager

### Phase 2: Playbook Flow 引擎
1. ⏳ 定義 Flow 結構
2. ⏳ 實現 FlowExecutor
3. ⏳ 實現依賴檢查和節點調度

### Phase 3: 最小 Flow 實作
1. ⏳ 實作 `web_page_flow`（A → B）
2. ⏳ 修改 `page_outline` playbook
3. ⏳ 修改 `threejs_hero_landing` playbook
4. ⏳ 測試完整流程

### Phase 4: 擴展 Flow
1. ⏳ 加入節點 C（sections_react）
2. ⏳ 實現平行執行
3. ⏳ 測試依賴和 artifact 共享

### Phase 5: UI 和跨 Workspace
1. ⏳ Project 視圖 UI
2. ⏳ Workspace 中的 Project 卡片
3. ⏳ Project 移交功能

## 🔗 與 Sandbox 系統整合

### Project Sandbox Manager

Project 使用統一的 SandboxManager，但有自己的 sandbox 空間：

```python
class ProjectSandboxManager:
    def get_project_sandbox(self, project_id: str) -> Sandbox:
        sandbox_id = f"{project_type}/{project_id}"
        return self.sandbox_manager.get_sandbox(sandbox_id)
```

### 統一的 Sandbox 能力

- 所有 Project 的 sandbox 都支持版本管理
- 所有 Project 的 sandbox 都支持變更可視化
- 所有 Project 的 sandbox 都支持局部修改

## 📚 相關文檔

### 核心文檔
- [Project + Flow 架構設計](project-flow-architecture.md) - 完整架構設計
- [Project + Flow 實作步驟](project-flow-implementation-steps.md) - 詳細實作指南

### 相關系統
- [Sandbox 系統架構設計](../sandbox/sandbox-system-architecture.md) - Sandbox 系統設計
- [Sandbox 系統實作步驟](../sandbox/sandbox-system-implementation-steps.md) - Sandbox 實作指南

### 具體場景
- [Three.js Sandbox 實作規劃](../threejs/threejs-sandbox-implementation-plan.md) - Three.js 場景
- [Three.js Sandbox 程式碼範例](../threejs/threejs-sandbox-code-examples.md) - 程式碼參考

## 🚀 開始實作

### 第一步：理解架構

1. 閱讀 [Project + Flow 架構設計](project-flow-architecture.md)
2. 理解 Project、Flow、Shared Sandbox 的關係
3. 查看「做一個網頁」的完整示範

### 第二步：實作基礎

1. 創建 Project 資料結構
2. 實現 ProjectManager
3. 實現 ArtifactRegistry

### 第三步：實作 Flow

1. 定義第一個 Flow（web_page_flow）
2. 實現 FlowExecutor
3. 測試最小流程（A → B）

## 💡 關鍵洞察

### 收斂一句話

> **凡是 AI 幫你改東西的場合，都應該經過 sandbox 這一層。**
>
> **凡是多個 playbook 協作完成一個作品的場合，都應該用 Project + Flow 來組織。**
>
> 這樣你的「多工 agent」就從「一群人各自拿到關鍵字瞎忙」變成「在同一個工地、看同一張藍圖、各做各工種，但共用同一組 artefact」。

---

**這是讓心智空間從「各自做夢」到「一起蓋房子」的關鍵架構！** 🏗️


# Project + Playbook Flow + Shared Sandbox 架構設計

## 🎯 核心問題

### 現狀痛點

1. **沒有「共同世界」**
   - 每個 playbook 各自憑輸入想像，沒有一份「唯一真實版本」的 spec/檔案

2. **沒有「先後關係」**
   - 一堆 playbook 同時被意圖打開、各自跑
   - LLM 在腦內排順序，但執行引擎沒有真的 enforce

3. **沒有「作品級別」的容器**
   - workspace 裡混了：這裡一個 hero，那裡一段影片，那邊一個 IG 文案
   - 其實要的是：「這些東西是同一個『作品』底下的部件」

### 解決方案

引入三個一級概念：
1. **Project / Work Unit** - 作品級容器
2. **Playbook Flow** - Playbook 群組/pipeline
3. **Shared Sandbox** - 作品級的檔案世界

## 🏗️ 架構設計

### 整體架構

```
┌─────────────────────────────────────────┐
│  Intent Layer                           │
│  "幫我做一個關於 xxx 的網頁"              │
│  → 判定: web_page_project                │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Orchestrator                           │
│  - 建立 Project                          │
│  - 掛上 Playbook Flow                    │
│  - 管理執行順序和依賴                     │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Project                                │
│  - id: web_page_2025xxxx                │
│  - type: web_page                       │
│  - flow_id: web_page_flow              │
│  - state: active                        │
│  - workspace_id: current                │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Playbook Flow                          │
│  Nodes:                                 │
│    A: page_outline_md                   │
│    B: hero_threejs                      │
│    C: sections_react                    │
│  Edges:                                 │
│    A -> B (B 要吃 A 的 md_spec)          │
│    A -> C (C 也吃 A 的 md_spec)          │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Shared Sandbox                         │
│  sandboxes/web_page/{project_id}/       │
│    spec/                                 │
│      page.md (A 產出)                    │
│    hero/                                 │
│      index.html (B 產出)                 │
│    sections/                             │
│      App.tsx (C 產出)                    │
└─────────────────────────────────────────┘
```

## 📦 核心概念

### 1. Project / Work Unit（作品 / 工地）

**定義：**
每次用戶說「幫我做一個關於 xxx 的網頁」，系統先建立一個 Project，所有後續檔案、sandbox、playbook 執行都掛在這個 project 底下。

**結構：**
```python
class Project:
    id: str                    # web_page_2025xxxx
    type: str                  # web_page, book, course, video
    title: str                 # "關於 xxx 的網頁"
    workspace_id: str          # 所屬 workspace
    flow_id: str               # web_page_flow
    state: str                 # active, completed, paused
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]   # 額外信息
```

**資料表設計：**
```sql
CREATE TABLE projects (
    id VARCHAR(255) PRIMARY KEY,
    type VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    workspace_id VARCHAR(255) NOT NULL,
    flow_id VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    metadata JSONB
);
```

### 2. Playbook Flow（Playbook 群組 / pipeline）

**定義：**
不是一堆 playbook 平行亂跑，而是定義節點和邊，執行單位是「這個 Project 正在跑 web_page_flow，現在在 A 節點」。

**結構：**
```python
class PlaybookFlow:
    id: str                    # web_page_flow
    name: str                  # "網頁製作流程"
    description: str
    nodes: List[FlowNode]      # 節點列表
    edges: List[FlowEdge]       # 邊列表（依賴關係）


class FlowNode:
    id: str                    # page_outline_md
    playbook_code: str         # 對應的 playbook
    name: str                  # "頁面大綱"
    inputs: List[ArtifactRef]   # 需要的 artifact
    outputs: List[ArtifactRef] # 產出的 artifact


class FlowEdge:
    from_node: str             # A
    to_node: str               # B
    artifact_ref: ArtifactRef   # B 需要 A 的 page_md
```

**範例：web_page_flow**
```yaml
flow_id: web_page_flow
name: 網頁製作流程

nodes:
  - id: page_outline_md
    playbook_code: page_outline
    name: 頁面大綱
    inputs: []
    outputs:
      - artifact_id: page_md
        path: spec/page.md
        type: markdown.page_spec

  - id: hero_threejs
    playbook_code: threejs_hero_landing
    name: Three.js Hero
    inputs:
      - artifact_id: page_md
        as: page_spec
    outputs:
      - artifact_id: hero_preview
        path: hero/index.html
        type: threejs.hero

  - id: sections_react
    playbook_code: react_sections
    name: React Sections
    inputs:
      - artifact_id: page_md
        as: page_spec
    outputs:
      - artifact_id: sections_app
        path: sections/App.tsx
        type: react.component

edges:
  - from: page_outline_md
    to: hero_threejs
    artifact: page_md

  - from: page_outline_md
    to: sections_react
    artifact: page_md
```

### 3. Shared Sandbox（作品級的檔案世界）

**定義：**
對這個 Project 開一個專屬 sandbox，所有 playbook 都寫進同一個 project sandbox，檔案共享機制自然存在。

**結構：**
```
sandboxes/web_page/{project_id}/
├── spec/
│   ├── page.md                    # A 產出
│   └── component_manifest.json
├── hero/
│   ├── index.html                  # B 產出
│   └── Component.tsx
├── sections/
│   ├── App.tsx                     # C 產出
│   └── components/
│       ├── Section1.tsx
│       └── Section2.tsx
└── meta.json
```

**Artifact Registry：**
```json
{
  "artifacts": [
    {
      "artifact_id": "page_md",
      "path": "spec/page.md",
      "type": "markdown.page_spec",
      "created_by": "page_outline_md",
      "created_at": "2025-01-01T00:00:00Z"
    },
    {
      "artifact_id": "hero_preview",
      "path": "hero/index.html",
      "type": "threejs.hero",
      "created_by": "hero_threejs",
      "created_at": "2025-01-01T00:05:00Z",
      "dependencies": ["page_md"]
    }
  ]
}
```

## 🔄 執行流程

### Step 0: 用戶一句話

```
用戶：「幫我做一個關於『城市覺知』的網頁，主題放在 XXX。」
```

Intent layer 判定：`web_page_project`

→ Orchestrator 建立一個 Project + 掛上 `web_page_flow`

### Step 1: 節點 A – Page Outline Playbook

**責任：**
1. 根據用戶需求 + 既有品牌 context
2. 出一份 `page.md`：
   - 頁首文案、hero tagline
   - 各 section 的標題 / 目的 / 敘事節奏
   - 哪些地方需要互動畫面、哪裡要 plain text
3. 寫入：`sandboxes/web_page/{project_id}/spec/page.md`
4. 在 Project 的 artifact registry 裡登記

**執行：**
```python
# Orchestrator 執行節點 A
node_a = flow.get_node("page_outline_md")
playbook = get_playbook(node_a.playbook_code)

# 執行 playbook
result = await playbook.execute(
    project_id=project.id,
    project_sandbox=sandbox,
    inputs={}
)

# 註冊 artifact
await project.register_artifact(
    artifact_id="page_md",
    path="spec/page.md",
    type="markdown.page_spec",
    created_by=node_a.id
)

# Flow 知道 A 完成了，才會排 B/C
await flow.mark_node_complete("page_outline_md")
```

### Step 2: 節點 B & C – Hero + Sections

#### B: three.js hero playbook

**宣告依賴：**
```yaml
inputs:
  - artifact: page_md
    as: page_spec
```

**執行：**
```python
# Orchestrator 檢查依賴
node_b = flow.get_node("hero_threejs")
dependencies = flow.get_dependencies(node_b.id)

# 讀取依賴的 artifact
page_md = await project.read_artifact("page_md")

# 執行 playbook
result = await playbook.execute(
    project_id=project.id,
    project_sandbox=sandbox,
    inputs={
        "page_spec": page_md
    }
)

# 註冊 artifact
await project.register_artifact(
    artifact_id="hero_preview",
    path="hero/index.html",
    type="threejs.hero",
    created_by=node_b.id,
    dependencies=["page_md"]
)
```

#### C: React sections playbook

**同樣流程：**
- 讀取 `page_md`
- 執行 playbook
- 產出 `sections/App.tsx`
- 註冊 artifact

**平行執行：**
B 和 C 可以平行跑（因為都只依賴 A），但兩個吃的 spec 是同一份 `page.md`。

### Step 3: Workspace UI 呈現

**Workspace 視圖：**
```
┌─────────────────────────────────────────┐
│  Workspace: 總控                        │
├─────────────────────────────────────────┤
│  🧱 Web Page Project – 城市覺知         │
│  流程：Outline → Hero → Sections         │
│  現況：Hero 已完成草稿、Sections 50%     │
│  [查看詳情] [移交到 Web Design WS]      │
└─────────────────────────────────────────┘
```

**Project 視圖：**
```
┌─────────────────────────────────────────┐
│  Project: 城市覺知網頁                  │
├─────────────────────────────────────────┤
│  [頁面大綱] [Hero] [Sections] [變更歷史]│
├─────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐      │
│  │ page.md     │  │ Hero Preview │      │
│  │ 預覽        │  │ (Three.js)   │      │
│  └─────────────┘  └─────────────┘      │
│                                         │
│  版本時間線：                            │
│  [v1] [v2] [v3]                        │
└─────────────────────────────────────────┘
```

## 🔀 跨 Workspace 的 Project 搬家

### 設計

**Project 有 `home_workspace_id`：**
- 一開始在「總控 workspace」被建立
- 可以在 UI 上選擇：「把這個 Project 拆出去，掛到『Web Design Workspace』」

**底層操作：**
```python
# 移交 Project 到另一個 workspace
await project.transfer_to_workspace(
    project_id=project.id,
    target_workspace_id="web_design_workspace"
)

# 原 workspace 只留下「成果卡」和「shortcut」
# 新 workspace 擁有完整的 Project 視圖
```

**好處：**
- 總控 workspace 不會被各種產物塞爆，只留「作品入口 & 狀態」
- 各專門 workspace（寫書、做網頁、剪影片）都有自己的 Project 清單和工具面板

## 🎯 與 Sandbox 系統整合

### Project Sandbox Manager

```python
class ProjectSandboxManager:
    """Project 專屬的 Sandbox 管理器"""

    def __init__(self, sandbox_manager: SandboxManager):
        self.sandbox_manager = sandbox_manager

    def get_project_sandbox(
        self,
        project_id: str,
        project_type: str
    ) -> Sandbox:
        """獲取或創建 Project 的 sandbox"""
        sandbox_id = f"{project_type}/{project_id}"

        # 使用統一的 SandboxManager
        sandbox = self.sandbox_manager.get_sandbox(sandbox_id)

        if not sandbox:
            sandbox = self.sandbox_manager.create_sandbox(
                sandbox_type=project_type,
                context={"project_id": project_id},
                workspace_id=project.workspace_id
            )

        return sandbox

    def write_artifact(
        self,
        project_id: str,
        artifact_id: str,
        path: str,
        content: str,
        artifact_type: str
    ):
        """寫入 artifact 到 Project sandbox"""
        sandbox = self.get_project_sandbox(project_id)

        # 使用統一的 write_file
        await sandbox.write_file(path, content)

        # 註冊到 artifact registry
        await project.register_artifact(
            artifact_id=artifact_id,
            path=path,
            type=artifact_type
        )

    def read_artifact(
        self,
        project_id: str,
        artifact_id: str
    ) -> str:
        """從 Project sandbox 讀取 artifact"""
        artifact = await project.get_artifact(artifact_id)
        sandbox = self.get_project_sandbox(project_id)

        return await sandbox.read_file(artifact.path)
```

## 📋 實作優先級

### Phase 1: Project 基礎層
1. ✅ 定義 `Project` 資料結構
2. ✅ 實現 `ProjectManager`
3. ✅ 實現 `ProjectSandboxManager`
4. ✅ 基本的 CRUD 操作

### Phase 2: Playbook Flow
1. ⏳ 定義 `PlaybookFlow` 結構
2. ⏳ 實現 Flow 執行引擎
3. ⏳ 實現依賴檢查和節點調度
4. ⏳ 實現 artifact registry

### Phase 3: 最小 Flow 實作
1. ⏳ 實作 `web_page_flow`（A → B）
2. ⏳ 修改 `page_outline` playbook 支持 Project
3. ⏳ 修改 `threejs_hero_landing` playbook 支持 Project
4. ⏳ 測試完整流程

### Phase 4: 擴展 Flow
1. ⏳ 加入節點 C（sections_react）
2. ⏳ 實現平行執行（B 和 C）
3. ⏳ 測試依賴和 artifact 共享

### Phase 5: UI 和跨 Workspace
1. ⏳ Project 視圖 UI
2. ⏳ Workspace 中的 Project 卡片
3. ⏳ Project 移交功能
4. ⏳ 變更歷史和時間線

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

## 📚 相關文檔

- [Sandbox 系統架構設計](../sandbox/sandbox-system-architecture.md)
- [Project + Flow 實作步驟](project-flow-implementation-steps.md)
- [Project + Flow 設計總結](project-flow-summary.md)


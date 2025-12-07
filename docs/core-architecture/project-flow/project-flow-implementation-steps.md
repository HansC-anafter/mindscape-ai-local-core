# Project + Playbook Flow 實作步驟

## 🎯 實作路徑

從現有狀態演進到 Project + Flow 架構的詳細步驟。

## 📋 Phase 1: Project 基礎層

### Step 1.1: 定義 Project 資料結構

**文件：** `backend/app/models/project.py`

```python
from sqlalchemy import Column, String, DateTime, JSON
from datetime import datetime
from backend.app.models.base import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(255), primary_key=True)
    type = Column(String(100), nullable=False)  # web_page, book, course
    title = Column(String(500), nullable=False)
    workspace_id = Column(String(255), nullable=False)
    flow_id = Column(String(255), nullable=False)
    state = Column(String(50), nullable=False)  # active, completed, paused
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata = Column(JSON, default={})
```

### Step 1.2: 實現 ProjectManager

**文件：** `backend/app/services/project/project_manager.py`

**核心功能：**
- `create_project()` - 創建新 Project
- `get_project()` - 獲取 Project
- `update_project()` - 更新 Project
- `list_projects()` - 列出 Projects
- `transfer_project()` - 移交 Project 到另一個 workspace

**實現：**
```python
class ProjectManager:
    def __init__(self, db_session):
        self.db = db_session

    async def create_project(
        self,
        project_type: str,
        title: str,
        workspace_id: str,
        flow_id: str,
        metadata: Optional[Dict] = None
    ) -> Project:
        """創建新 Project"""
        project_id = generate_project_id(project_type)

        project = Project(
            id=project_id,
            type=project_type,
            title=title,
            workspace_id=workspace_id,
            flow_id=flow_id,
            state="active",
            metadata=metadata or {}
        )

        self.db.add(project)
        self.db.commit()

        return project
```

### Step 1.3: 實現 Artifact Registry

**文件：** `backend/app/services/project/artifact_registry.py`

**功能：**
- 註冊 artifact
- 查詢 artifact
- 追蹤依賴關係

**結構：**
```python
class ArtifactRegistry:
    def __init__(self, db_session):
        self.db = db_session

    async def register_artifact(
        self,
        project_id: str,
        artifact_id: str,
        path: str,
        artifact_type: str,
        created_by: str,
        dependencies: Optional[List[str]] = None
    ):
        """註冊 artifact"""
        artifact = Artifact(
            project_id=project_id,
            artifact_id=artifact_id,
            path=path,
            type=artifact_type,
            created_by=created_by,
            dependencies=dependencies or []
        )

        self.db.add(artifact)
        self.db.commit()

    async def get_artifact(
        self,
        project_id: str,
        artifact_id: str
    ) -> Artifact:
        """獲取 artifact"""
        return self.db.query(Artifact).filter(
            Artifact.project_id == project_id,
            Artifact.artifact_id == artifact_id
        ).first()
```

### Step 1.4: 實現 ProjectSandboxManager

**文件：** `backend/app/services/project/project_sandbox_manager.py`

**功能：**
- 獲取或創建 Project 的 sandbox
- 統一的 artifact 讀寫接口
- 與 SandboxManager 整合

**實現：**
```python
class ProjectSandboxManager:
    def __init__(
        self,
        sandbox_manager: SandboxManager,
        project_manager: ProjectManager
    ):
        self.sandbox_manager = sandbox_manager
        self.project_manager = project_manager

    async def get_project_sandbox(
        self,
        project_id: str
    ) -> Sandbox:
        """獲取或創建 Project 的 sandbox"""
        project = await self.project_manager.get_project(project_id)

        sandbox_id = f"{project.type}/{project_id}"

        # 使用統一的 SandboxManager
        sandbox = self.sandbox_manager.get_sandbox(sandbox_id)

        if not sandbox:
            sandbox = await self.sandbox_manager.create_sandbox(
                sandbox_type=project.type,
                context={"project_id": project_id},
                workspace_id=project.workspace_id
            )

        return sandbox
```

## 📋 Phase 2: Playbook Flow 引擎

### Step 2.1: 定義 Flow 結構

**文件：** `backend/app/models/playbook_flow.py`

```python
class PlaybookFlow(Base):
    __tablename__ = "playbook_flows"

    id = Column(String(255), primary_key=True)
    name = Column(String(500))
    description = Column(String(2000))
    flow_definition = Column(JSON)  # 包含 nodes 和 edges
    created_at = Column(DateTime, default=datetime.utcnow)
```

**Flow 定義格式：**
```json
{
  "nodes": [
    {
      "id": "page_outline_md",
      "playbook_code": "page_outline",
      "name": "頁面大綱",
      "inputs": [],
      "outputs": [
        {
          "artifact_id": "page_md",
          "path": "spec/page.md",
          "type": "markdown.page_spec"
        }
      ]
    }
  ],
  "edges": [
    {
      "from": "page_outline_md",
      "to": "hero_threejs",
      "artifact": "page_md"
    }
  ]
}
```

### Step 2.2: 實現 Flow 執行引擎

**文件：** `backend/app/services/project/flow_executor.py`

**核心功能：**
- 解析 Flow 定義
- 檢查依賴
- 調度節點執行
- 管理執行狀態

**實現：**
```python
class FlowExecutor:
    def __init__(
        self,
        project_manager: ProjectManager,
        project_sandbox_manager: ProjectSandboxManager,
        artifact_registry: ArtifactRegistry
    ):
        self.project_manager = project_manager
        self.sandbox_manager = project_sandbox_manager
        self.artifact_registry = artifact_registry

    async def execute_flow(
        self,
        project_id: str
    ):
        """執行 Project 的 Flow"""
        project = await self.project_manager.get_project(project_id)
        flow = await self.get_flow(project.flow_id)

        # 獲取 Project sandbox
        sandbox = await self.sandbox_manager.get_project_sandbox(project_id)

        # 執行節點（按依賴順序）
        completed_nodes = set()
        ready_nodes = self.get_ready_nodes(flow, completed_nodes)

        while ready_nodes:
            # 平行執行所有 ready 的節點
            tasks = [
                self.execute_node(project, flow, node, sandbox)
                for node in ready_nodes
            ]
            results = await asyncio.gather(*tasks)

            # 更新完成狀態
            for node in ready_nodes:
                completed_nodes.add(node.id)

            # 找出下一批 ready 的節點
            ready_nodes = self.get_ready_nodes(flow, completed_nodes)

    async def execute_node(
        self,
        project: Project,
        flow: PlaybookFlow,
        node: FlowNode,
        sandbox: Sandbox
    ):
        """執行單個節點"""
        # 1. 讀取依賴的 artifacts
        inputs = {}
        for input_ref in node.inputs:
            artifact = await self.artifact_registry.get_artifact(
                project.id,
                input_ref.artifact_id
            )
            content = await sandbox.read_file(artifact.path)
            inputs[input_ref.as] = content

        # 2. 執行 playbook
        playbook = get_playbook(node.playbook_code)
        result = await playbook.execute(
            project_id=project.id,
            project_sandbox=sandbox,
            inputs=inputs
        )

        # 3. 註冊產出的 artifacts
        for output_ref in node.outputs:
            await self.artifact_registry.register_artifact(
                project_id=project.id,
                artifact_id=output_ref.artifact_id,
                path=output_ref.path,
                artifact_type=output_ref.type,
                created_by=node.id,
                dependencies=[inp.artifact_id for inp in node.inputs]
            )
```

## 📋 Phase 3: 最小 Flow 實作

### Step 3.1: 定義 web_page_flow

**文件：** `backend/playbooks/flows/web_page_flow.yaml`

```yaml
flow_id: web_page_flow
name: 網頁製作流程
description: 從大綱到 Hero 到 Sections 的完整流程

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

edges:
  - from: page_outline_md
    to: hero_threejs
    artifact: page_md
```

### Step 3.2: 修改 page_outline Playbook

**變更：**
- 接受 `project_id` 和 `project_sandbox` 參數
- 產物寫入 Project sandbox
- 註冊 artifact

**範例：**
```python
# 在 playbook 執行中
async def execute_page_outline(
    project_id: str,
    project_sandbox: Sandbox,
    user_input: str
):
    # 生成 page.md
    page_md = await generate_page_outline(user_input)

    # 寫入 Project sandbox
    await project_sandbox.write_file(
        "spec/page.md",
        page_md
    )

    # 註冊 artifact（由 FlowExecutor 處理）
    # 這裡只需要返回 artifact 信息
    return {
        "artifacts": [
            {
                "artifact_id": "page_md",
                "path": "spec/page.md",
                "type": "markdown.page_spec"
            }
        ]
    }
```

### Step 3.3: 修改 threejs_hero_landing Playbook

**變更：**
- 接受 `project_id` 和 `project_sandbox` 參數
- 接受 `page_spec` 作為輸入（從 artifact 讀取）
- 產物寫入 Project sandbox

**範例：**
```python
# 在 playbook 執行中
async def execute_hero(
    project_id: str,
    project_sandbox: Sandbox,
    page_spec: str  # 從 artifact 讀取
):
    # 基於 page_spec 生成 hero
    hero_code = await generate_hero(page_spec)

    # 寫入 Project sandbox
    await project_sandbox.write_file(
        "hero/index.html",
        hero_code
    )

    return {
        "artifacts": [
            {
                "artifact_id": "hero_preview",
                "path": "hero/index.html",
                "type": "threejs.hero"
            }
        ]
    }
```

### Step 3.4: 測試完整流程

**測試腳本：**
```python
async def test_web_page_flow():
    # 1. 創建 Project
    project = await project_manager.create_project(
        project_type="web_page",
        title="城市覺知網頁",
        workspace_id="workspace-123",
        flow_id="web_page_flow"
    )

    # 2. 執行 Flow
    executor = FlowExecutor(...)
    await executor.execute_flow(project.id)

    # 3. 驗證 artifacts
    page_md = await artifact_registry.get_artifact(project.id, "page_md")
    hero_preview = await artifact_registry.get_artifact(project.id, "hero_preview")

    assert page_md is not None
    assert hero_preview is not None
```

## 📋 Phase 4: 擴展 Flow

### Step 4.1: 加入節點 C（sections_react）

**更新 flow 定義：**
```yaml
nodes:
  # ... A 和 B ...

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

### Step 4.2: 實現平行執行

**FlowExecutor 改進：**
```python
async def execute_flow(self, project_id: str):
    # ...

    # 找出可以平行執行的節點
    ready_nodes = self.get_ready_nodes(flow, completed_nodes)

    # 平行執行
    tasks = [
        self.execute_node(project, flow, node, sandbox)
        for node in ready_nodes
    ]
    await asyncio.gather(*tasks)
```

## 📋 Phase 5: UI 和跨 Workspace

### Step 5.1: Project 視圖 UI

**文件：** `web-console/src/components/Project/ProjectView.tsx`

**功能：**
- 顯示 Project 信息
- 顯示 Flow 進度
- 顯示 Artifacts 列表
- 顯示變更歷史

### Step 5.2: Workspace 中的 Project 卡片

**文件：** `web-console/src/components/Workspace/ProjectCard.tsx`

**功能：**
- 顯示 Project 摘要
- 顯示進度狀態
- 快速操作（查看、移交）

### Step 5.3: Project 移交功能

**API：**
```python
@router.post("/projects/{project_id}/transfer")
async def transfer_project(
    project_id: str,
    target_workspace_id: str
):
    await project_manager.transfer_project(
        project_id=project_id,
        target_workspace_id=target_workspace_id
    )
```

## 🔧 技術細節

### Intent 到 Project 的映射

**Intent Handler：**
```python
class IntentHandler:
    async def handle_intent(
        self,
        intent: str,
        user_input: str,
        workspace_id: str
    ):
        # 判定 Project 類型和 Flow
        if intent == "web_page_project":
            project_type = "web_page"
            flow_id = "web_page_flow"
        elif intent == "book_project":
            project_type = "book"
            flow_id = "book_flow"
        # ...

        # 創建 Project
        project = await project_manager.create_project(
            project_type=project_type,
            title=extract_title(user_input),
            workspace_id=workspace_id,
            flow_id=flow_id
        )

        # 執行 Flow
        executor = FlowExecutor(...)
        await executor.execute_flow(project.id)

        return project
```

### Playbook 適配器

**為了向後兼容，創建 Playbook 適配器：**
```python
class ProjectPlaybookAdapter:
    """將現有 Playbook 適配到 Project 模式"""

    async def execute(
        self,
        playbook_code: str,
        project_id: str,
        project_sandbox: Sandbox,
        inputs: Dict[str, Any]
    ):
        # 獲取原始 playbook
        playbook = get_playbook(playbook_code)

        # 包裝執行上下文
        context = {
            "project_id": project_id,
            "project_sandbox": project_sandbox,
            "inputs": inputs
        }

        # 執行 playbook（可能需要修改 playbook 以支持新參數）
        return await playbook.execute_with_project_context(context)
```

## 📋 實作檢查清單

### Phase 1: Project 基礎
- [ ] 定義 Project 資料表
- [ ] 實現 ProjectManager
- [ ] 實現 ArtifactRegistry
- [ ] 實現 ProjectSandboxManager
- [ ] 基本 CRUD API

### Phase 2: Flow 引擎
- [ ] 定義 Flow 資料結構
- [ ] 實現 FlowExecutor
- [ ] 實現依賴檢查
- [ ] 實現節點調度

### Phase 3: 最小 Flow
- [ ] 定義 web_page_flow
- [ ] 修改 page_outline playbook
- [ ] 修改 threejs_hero_landing playbook
- [ ] 測試完整流程

### Phase 4: 擴展
- [ ] 加入 sections_react 節點
- [ ] 實現平行執行
- [ ] 測試依賴和共享

### Phase 5: UI
- [ ] Project 視圖
- [ ] Workspace Project 卡片
- [ ] Project 移交功能

## 🚀 開始實作

### 第一步：創建 Project 基礎

```bash
cd mindscape-ai-local-core/backend/app
mkdir -p models services/project
```

### 第二步：實現 ProjectManager

參考 [Project + Flow 架構設計](project-flow-architecture.md) 中的設計。

### 第三步：定義第一個 Flow

從 `web_page_flow` 開始，只包含兩個節點（A → B）。

## 📚 相關文檔

- [Project + Flow 架構設計](project-flow-architecture.md)
- [Project + Flow 設計總結](project-flow-summary.md)
- [Sandbox 系統架構設計](../sandbox/sandbox-system-architecture.md)
- [Playbook Flow 定義規範](playbook-flow-spec.md)（待創建）


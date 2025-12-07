# Sandbox 系統實作步驟

## 🎯 目標

將 sandbox 提升為系統級能力，統一所有 AI 寫入操作。

## 📋 實作階段

### Phase 1: 系統級 SandboxManager（核心基礎）

#### Step 1.1: 創建核心架構

**目錄結構：**
```
mindscape-ai-local-core/backend/app/services/sandbox/
├── __init__.py
├── manager.py              # SandboxManager 核心
├── base.py                  # Sandbox 基類
├── version_manager.py       # 版本管理（統一）
├── storage/
│   ├── __init__.py
│   ├── local_storage.py     # Local 存儲實現
│   └── cloud_storage.py     # Cloud 存儲實現（未來）
└── types/
    ├── __init__.py
    ├── threejs_hero.py      # Three.js Hero Sandbox
    ├── writing_project.py   # 書稿 Sandbox
    └── project_repo.py      # 專案 Repo Sandbox
```

#### Step 1.2: 實現 SandboxManager 核心

**文件：** `manager.py`

**核心功能：**
- `create_sandbox()` - 創建 sandbox（根據類型選擇對應實現）
- `get_sandbox()` - 獲取 sandbox 實例
- `read_file()` - 統一讀取接口
- `write_file()` - 統一寫入接口（自動版本管理）
- `apply_patch()` - 統一 patch 接口
- `list_versions()` - 統一版本列表
- `get_diff()` - 統一 diff 接口

**關鍵設計：**
```python
class SandboxManager:
    """系統級的 Sandbox 管理器"""

    def __init__(self, storage_backend: StorageBackend):
        self.storage = storage_backend
        self.sandbox_registry = {}  # 註冊不同類型的 sandbox 實現

    def register_sandbox_type(
        self,
        sandbox_type: str,
        sandbox_class: Type[Sandbox]
    ):
        """註冊 sandbox 類型"""
        self.sandbox_registry[sandbox_type] = sandbox_class

    def create_sandbox(
        self,
        sandbox_type: str,
        context: Dict[str, Any],
        workspace_id: str
    ) -> Sandbox:
        """創建 sandbox（根據類型選擇對應實現）"""
        if sandbox_type not in self.sandbox_registry:
            raise ValueError(f"Unknown sandbox type: {sandbox_type}")

        sandbox_class = self.sandbox_registry[sandbox_type]
        return sandbox_class.create(
            storage=self.storage,
            context=context,
            workspace_id=workspace_id
        )
```

#### Step 1.3: 實現統一版本管理

**文件：** `version_manager.py`

**功能：**
- 所有 sandbox 類型共享相同的版本管理邏輯
- 自動創建版本（每次寫入可選）
- 版本元數據統一格式
- 統一的 diff 計算

**版本元數據格式：**
```json
{
  "version": "v2",
  "created_at": "2024-01-01T00:00:00Z",
  "created_by": "ai",
  "modification_prompt": "粒子密度減半但保留現在顏色",
  "change_summary": {
    "type": "modification",
    "changes": [
      "粒子數量從 300 減少為 150",
      "線條透明度略降低"
    ]
  },
  "files": {
    "Component.tsx": {
      "path": "versions/v2/Component.tsx",
      "size": 12345,
      "checksum": "abc123..."
    }
  }
}
```

#### Step 1.4: 實現存儲抽象

**文件：** `storage/local_storage.py`

**功能：**
- 統一的文件讀寫接口
- 路徑驗證和安全檢查
- 支持符號鏈接（current version）

**接口：**
```python
class StorageBackend(ABC):
    """存儲後端抽象"""

    @abstractmethod
    def read_file(self, path: Path) -> str:
        pass

    @abstractmethod
    def write_file(self, path: Path, content: str):
        pass

    @abstractmethod
    def list_files(self, path: Path) -> List[Path]:
        pass

    @abstractmethod
    def create_symlink(self, target: Path, link: Path):
        pass


class LocalStorageBackend(StorageBackend):
    """Local 文件系統實現"""
    pass
```

### Phase 2: 實現具體 Sandbox 類型

#### Step 2.1: Three.js Hero Sandbox

**文件：** `types/threejs_hero.py`

**特點：**
- 繼承 `Sandbox` 基類
- 實現 `get_preview_url()`
- 實現 `get_file_structure()`
- 實現 `validate_patch()`

**工具映射：**
- `sandbox.threejs.create_scene` → `create_sandbox(type="threejs_hero")`
- `sandbox.threejs.read_scene` → `read_file()`
- `sandbox.threejs.apply_patch` → `apply_patch()`

#### Step 2.2: Writing Project Sandbox

**文件：** `types/writing_project.py`

**特點：**
- 支持章節結構
- 支持大綱管理
- 特殊的文件組織方式

**工具映射：**
- `sandbox.writing.create_project` → `create_sandbox(type="writing_project")`
- `sandbox.writing.create_chapter` → `write_file()` + 特殊邏輯
- `sandbox.writing.read_section` → `read_file()`
- `sandbox.writing.apply_patch` → `apply_patch()`

#### Step 2.3: Project Repo Sandbox

**文件：** `types/project_repo.py`

**特點：**
- 可以是 git branch 或獨立目錄
- 需要 merge 機制
- 支持 patch 集合

**工具映射：**
- `sandbox.project.plan_patch` → 分析並生成 patch 計劃
- `sandbox.project.apply_patch` → `apply_patch()` + git 操作
- `sandbox.project.merge_to_main` → 合併到 production（需要確認）

### Phase 3: 工具層重構

#### Step 3.1: 創建 Sandbox 工具基類

**文件：** `backend/app/services/tools/sandbox/sandbox_tool_base.py`

**功能：**
- 所有 sandbox 工具的基類
- 統一的錯誤處理
- 統一的日誌記錄

#### Step 3.2: 實現具體工具

**Three.js 工具：**
```python
class ThreeJSCreateSceneTool(SandboxToolBase):
    async def execute(self, slug: str, initial_prompt: str) -> Dict:
        sandbox = await self.sandbox_manager.create_sandbox(
            sandbox_type="threejs_hero",
            context={"slug": slug},
            workspace_id=self.workspace_id
        )
        # ... 生成初始場景代碼
        await sandbox.write_file("Component.tsx", code)
        return {"sandbox_id": sandbox.sandbox_id, ...}
```

**Writing 工具：**
```python
class WritingCreateChapterTool(SandboxToolBase):
    async def execute(self, project_id: str, chapter_title: str) -> Dict:
        sandbox = await self.sandbox_manager.get_sandbox(
            sandbox_id=f"writing_project/{project_id}"
        )
        # ... 生成章節內容
        await sandbox.write_file(f"ch{chapter_num}.md", content)
        return {"chapter_path": ..., ...}
```

### Phase 4: 遷移現有 Playbook

#### Step 4.1: 遷移 threejs_hero_landing

**變更：**
- 將 `filesystem_write_file` 改為 `sandbox.threejs.create_scene`
- 將後續修改改為 `sandbox.threejs.apply_patch`
- 更新 Playbook 文檔

#### Step 4.2: 遷移 yearly_personal_book

**變更：**
- 將 `filesystem_write_file` 改為 `sandbox.writing.create_project`
- 將章節創建改為 `sandbox.writing.create_chapter`
- 更新 Playbook 文檔

#### Step 4.3: 更新其他 Playbook

**策略：**
- 逐步遷移，保持向後兼容
- 舊的 `filesystem_write_file` 可以繼續使用（但會警告）
- 新的 Playbook 必須使用 sandbox

### Phase 5: 統一 UI 實現

#### Step 5.1: Sandbox Viewer 共用元件

**文件：** `web-console/src/components/Sandbox/SandboxViewer.tsx`

**功能：**
- 統一的頁籤結構（預覽 / 原始碼 / 變更歷史 / AI 對話）
- 根據 `sandbox_type` 選擇對應的 preview renderer
- 統一的版本時間線
- 統一的變更摘要顯示

#### Step 5.2: Preview Renderer

**Three.js Renderer：**
```tsx
<ThreeJSPreviewRenderer
  sandboxId={sandboxId}
  version={version}
  onVisualSelect={(region) => {
    // 視覺圈選處理
  }}
/>
```

**Writing Renderer：**
```tsx
<MarkdownPreviewRenderer
  sandboxId={sandboxId}
  version={version}
/>
```

**Project Renderer：**
```tsx
<CodeDiffRenderer
  sandboxId={sandboxId}
  fromVersion={v1}
  toVersion={v2}
/>
```

## 🔧 技術細節

### 局部修改實現

**統一的 Patch 格式：**
```python
@dataclass
class Patch:
    """統一的 Patch 格式"""
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    old_content: Optional[str] = None
    new_content: str
    selection_type: str = "code"  # code, visual, text
    selection_data: Optional[Dict] = None  # 視覺圈選數據
```

**應用邏輯：**
```python
async def apply_patch(
    self,
    sandbox_id: str,
    patch: Patch,
    target_version: Optional[str] = None
) -> Dict[str, Any]:
    """應用 patch（所有 sandbox 類型共享）"""
    # 1. 讀取目標版本
    current_files = self.get_version_files(sandbox_id, target_version)

    # 2. 應用 patch
    if patch.start_line and patch.end_line:
        # 行號範圍 patch
        new_content = apply_line_patch(
            current_files[patch.file_path],
            patch.start_line,
            patch.end_line,
            patch.new_content
        )
    else:
        # 全文替換
        new_content = patch.new_content

    # 3. 創建新版本
    new_version = self.create_version(sandbox_id, base_version=target_version)

    # 4. 寫入文件
    await self.write_file(sandbox_id, patch.file_path, new_content, create_version=False)

    # 5. 生成變更摘要
    change_summary = await self.generate_change_summary(
        old_files={patch.file_path: current_files[patch.file_path]},
        new_files={patch.file_path: new_content},
        modification_prompt=patch.modification_prompt
    )

    return {
        "new_version": new_version,
        "change_summary": change_summary
    }
```

### 變更摘要生成

**統一的摘要生成：**
```python
async def generate_change_summary(
    self,
    old_files: Dict[str, str],
    new_files: Dict[str, str],
    modification_prompt: str,
    sandbox_type: str
) -> Dict[str, Any]:
    """生成變更摘要（所有 sandbox 類型共享）"""

    # 計算 diff
    diff = compute_unified_diff(old_files, new_files)

    # 根據 sandbox_type 選擇不同的 prompt 模板
    prompt_template = get_summary_prompt_template(sandbox_type)

    summary_prompt = prompt_template.format(
        modification_prompt=modification_prompt,
        diff=diff
    )

    # 調用 LLM
    summary = await self.llm_client.generate(summary_prompt)

    return {
        "type": "modification",
        "prompt": modification_prompt,
        "changes": parse_summary_list(summary),
        "diff": diff
    }
```

## 📋 實作檢查清單

### Phase 1: 核心基礎
- [ ] 創建 `sandbox/` 目錄結構
- [ ] 實現 `SandboxManager` 核心類
- [ ] 實現 `Sandbox` 基類
- [ ] 實現統一版本管理
- [ ] 實現 Local 存儲後端
- [ ] 註冊 sandbox 類型系統

### Phase 2: 具體類型
- [ ] 實現 `ThreeJSHeroSandbox`
- [ ] 實現 `WritingProjectSandbox`
- [ ] 實現 `ProjectRepoSandbox`（可選）

### Phase 3: 工具層
- [ ] 創建 `SandboxToolBase`
- [ ] 實現 Three.js 工具
- [ ] 實現 Writing 工具
- [ ] 註冊工具到系統

### Phase 4: 遷移
- [ ] 遷移 `threejs_hero_landing` Playbook
- [ ] 遷移 `yearly_personal_book` Playbook
- [ ] 更新其他相關 Playbook

### Phase 5: UI
- [ ] 實現 `SandboxViewer` 共用元件
- [ ] 實現 Three.js preview renderer
- [ ] 實現 Markdown preview renderer
- [ ] 實現統一的變更可視化

## 🚀 開始實作

### 第一步：創建核心架構

```bash
cd mindscape-ai-local-core/backend/app/services
mkdir -p sandbox/{storage,types}
```

### 第二步：實現 SandboxManager

參考 [Sandbox 系統架構設計](sandbox-system-architecture.md) 中的設計。

### 第三步：實現第一個 Sandbox 類型

從 `threejs_hero` 開始，因為已經有詳細的規劃。

## 📚 相關文檔

- [Sandbox 系統架構設計](sandbox-system-architecture.md)
- [Sandbox 系統設計總結](sandbox-system-summary.md)
- [Project + Flow 架構設計](../project-flow/project-flow-architecture.md)
- [Three.js Sandbox 實作規劃](../threejs/threejs-sandbox-implementation-plan.md)
- [Three.js Sandbox 程式碼範例](../threejs/threejs-sandbox-code-examples.md)


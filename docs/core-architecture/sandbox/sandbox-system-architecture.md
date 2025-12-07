# Sandbox 系統架構設計

## 🎯 核心原則

### 鐵律：凡是「AI 寫入」，一律走 sandbox 流

```
✅ LLM 可以隨便讀檔（有權限的情況下）
❌ 但只要要寫 / 改檔，就必須透過 sandbox tool，不准直接寫實體檔案
```

### 為什麼？

1. **安全邊界清楚**
   - 一看 `sandbox_id` / `sandbox_root` 就知道：「這個改動只影響這一小塊世界」

2. **統一版本 / diff / 回滾機制**
   - 不用每一種 artefact 都再設計一套版本系統

3. **local / cloud 一致**
   - local 是資料夾
   - cloud 是 volume / bucket
   - 對 Playbook / Tool 來說都是 `sandbox.*` 介面

## 🏗️ 系統架構

### 架構層次

```
┌─────────────────────────────────────────┐
│  UI Layer                                │
│  - Sandbox Viewer (共用元件)             │
│  - 不同 sandbox_type 的 preview renderer │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Tool Layer                              │
│  - sandbox.threejs.create_scene          │
│  - sandbox.writing.create_chapter        │
│  - sandbox.project.apply_patch           │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  SandboxManager (系統級)                 │
│  - create_sandbox(type, context)         │
│  - read_file(sandbox_id, path)          │
│  - write_file(sandbox_id, path, content) │
│  - apply_patch(sandbox_id, patch)        │
│  - list_versions(sandbox_id)             │
│  - get_diff(sandbox_id, from, to)        │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  Storage Layer                           │
│  - Local: 檔案系統                       │
│  - Cloud: Volume / Bucket                │
└─────────────────────────────────────────┘
```

## 📦 Sandbox 類型

### 1. Three.js / 動畫 / Demo 類

**sandbox_type: `threejs_hero`**

**特點：**
- 視覺 + code 混合
- 需要 preview 和視覺圈選
- 結構：`versions/v1/Component.tsx`, `index.html`

**工具族：**
- `sandbox.threejs.create_scene`
- `sandbox.threejs.read_scene`
- `sandbox.threejs.apply_patch`

### 2. 文稿 / 筆記 / 書稿

**sandbox_type: `writing_project`**

**特點：**
- 純文字內容
- 結構化章節
- 結構：`outline.md`, `ch01.md`, `ch02.md`, `meta.json`

**工具族：**
- `sandbox.writing.create_project`
- `sandbox.writing.create_chapter`
- `sandbox.writing.read_section`
- `sandbox.writing.apply_patch`

**範例結構：**
```
writing/{project_id}/
├── outline.md
├── ch01.md
├── ch02.md
├── ...
└── meta.json
```

### 3. 專案 / 程式碼層（Repo 級）

**sandbox_type: `project_repo`**

**特點：**
- 可以是 patch 集合或專用 git branch
- 需要 merge 機制
- 結構：`patches/`, `branch/`, 或 `sandbox/` 目錄

**工具族：**
- `sandbox.project.plan_patch` → 產生 patch
- `sandbox.project.apply_patch` → 寫到 branch / sandbox 目錄
- `sandbox.project.merge_to_main` → 合併到 production（需要用戶確認）

**實作方式：**
- Option 1: 專用 git branch（`sandbox-{id}`）
- Option 2: 獨立目錄 + patch 集合
- Option 3: 虛擬檔案系統（只記錄變更）

## 🔧 統一 SandboxManager 設計

### 核心接口

```python
class SandboxManager:
    """系統級的 Sandbox 管理器"""

    def create_sandbox(
        self,
        sandbox_type: str,
        context: Dict[str, Any],
        workspace_id: str
    ) -> Sandbox:
        """
        創建新的 sandbox

        Args:
            sandbox_type: 類型（threejs_hero, writing_project, project_repo）
            context: 上下文信息（slug, project_name 等）
            workspace_id: 工作空間 ID

        Returns:
            Sandbox 實例
        """
        pass

    def read_file(
        self,
        sandbox_id: str,
        file_path: str,
        version: Optional[str] = None
    ) -> str:
        """讀取文件內容"""
        pass

    def write_file(
        self,
        sandbox_id: str,
        file_path: str,
        content: str,
        create_version: bool = True
    ) -> Dict[str, Any]:
        """
        寫入文件

        Args:
            create_version: 是否創建新版本（預設 True）

        Returns:
            {
                "version": "v2",
                "file_path": "...",
                "change_summary": {...}
            }
        """
        pass

    def apply_patch(
        self,
        sandbox_id: str,
        patch: Patch,
        target_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        應用 patch

        Args:
            patch: Patch 對象（包含 file_path, start_line, end_line, new_content）
            target_version: 目標版本（None 則使用當前版本）

        Returns:
            新版本信息和變更摘要
        """
        pass

    def list_versions(
        self,
        sandbox_id: str
    ) -> List[Dict[str, Any]]:
        """列出所有版本"""
        pass

    def get_diff(
        self,
        sandbox_id: str,
        from_version: str,
        to_version: str
    ) -> Dict[str, Any]:
        """獲取兩個版本的差異"""
        pass

    def get_current_version(
        self,
        sandbox_id: str
    ) -> Optional[str]:
        """獲取當前版本"""
        pass

    def set_current_version(
        self,
        sandbox_id: str,
        version: str
    ):
        """設置當前版本"""
        pass
```

### Sandbox 基類

```python
class Sandbox(ABC):
    """Sandbox 抽象基類"""

    def __init__(
        self,
        sandbox_id: str,
        sandbox_type: str,
        base_path: Path,
        metadata: Dict[str, Any]
    ):
        self.sandbox_id = sandbox_id
        self.sandbox_type = sandbox_type
        self.base_path = base_path
        self.metadata = metadata

    @abstractmethod
    def get_preview_url(self, version: str) -> Optional[str]:
        """獲取預覽 URL（如果適用）"""
        pass

    @abstractmethod
    def get_file_structure(self) -> Dict[str, Any]:
        """獲取文件結構描述"""
        pass

    @abstractmethod
    def validate_patch(self, patch: Patch) -> bool:
        """驗證 patch 是否有效"""
        pass
```

### 具體實現

```python
class ThreeJSHeroSandbox(Sandbox):
    """Three.js Hero Sandbox 實現"""

    def get_preview_url(self, version: str) -> Optional[str]:
        return f"http://localhost:8888/sandboxes/{self.sandbox_id}/versions/{version}/index.html"

    def get_file_structure(self) -> Dict[str, Any]:
        return {
            "Component.tsx": "React Three Fiber 組件",
            "index.html": "獨立預覽頁面",
            "config.json": "場景配置"
        }

    def validate_patch(self, patch: Patch) -> bool:
        # Three.js 特定的驗證邏輯
        return True


class WritingProjectSandbox(Sandbox):
    """書稿 Sandbox 實現"""

    def get_preview_url(self, version: str) -> Optional[str]:
        # 書稿可能不需要視覺預覽，或返回 markdown 渲染頁面
        return None

    def get_file_structure(self) -> Dict[str, Any]:
        return {
            "outline.md": "大綱",
            "ch*.md": "章節文件",
            "meta.json": "元數據"
        }

    def validate_patch(self, patch: Patch) -> bool:
        # 書稿特定的驗證邏輯
        return True
```

## 🔄 遷移現有工具

### 現狀：直接寫文件

```python
# 舊方式：直接寫文件
await filesystem_write_file(
    file_path="artifacts/threejs_hero_landing/{execution_id}/Component.tsx",
    content=generated_code
)
```

### 新方式：通過 Sandbox

```python
# 新方式：通過 sandbox
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

### 工具註冊方式

**舊方式：**
```yaml
tools:
  - name: filesystem_write_file
    type: filesystem
```

**新方式：**
```yaml
tools:
  - name: sandbox.threejs.create_scene
    type: sandbox
    sandbox_type: threejs_hero

  - name: sandbox.writing.create_chapter
    type: sandbox
    sandbox_type: writing_project
```

## 🎨 統一 UI 模式

### Sandbox Viewer 共用元件

所有 sandbox 類型共享相同的 UI 結構：

```
┌─────────────────────────────────────────┐
│  Sandbox Viewer                          │
├─────────────────────────────────────────┤
│  [預覽] [原始碼] [變更歷史] [AI 對話]    │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  預覽區域                        │   │
│  │  (根據 sandbox_type 渲染)        │   │
│  │  - threejs_hero → Three.js 預覽 │   │
│  │  - writing_project → Markdown   │   │
│  │  - project_repo → Code diff     │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  版本時間線                      │   │
│  │  [v1] [v2] [v3] [v4]            │   │
│  │                                 │   │
│  │  變更摘要：                      │   │
│  │  ✅ 粒子數量從 300 減少為 150    │   │
│  │  ✅ 線條透明度略降低              │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 局部修改模式

所有 sandbox 類型都支持局部修改：

1. **文字檔** → 選取範圍當 patch scope
2. **Code** → `start_line / end_line` + diff
3. **Three.js** → 視覺圈選 + mapping 到 config / 物件

### 變更可視化模式

所有 sandbox 類型共享：
- 版本時間線
- Before/After 對比
- AI 口語摘要

## 📋 實作優先級

### Phase 1: 系統級 SandboxManager（核心）

1. ✅ 設計統一的 `SandboxManager` 接口
2. ✅ 實現基礎的版本管理
3. ✅ 實現統一的 diff 和摘要生成
4. ✅ 支持 local 和 cloud 兩種存儲

### Phase 2: 遷移現有工具

1. ⏳ 將 `threejs_hero_landing` 遷移到 sandbox 模式
2. ⏳ 將 `yearly_personal_book` 遷移到 sandbox 模式
3. ⏳ 更新所有使用 `filesystem_write_file` 的 Playbook

### Phase 3: 新增 Sandbox 類型

1. ⏳ 實現 `project_repo` sandbox 類型
2. ⏳ 實現其他需要的 sandbox 類型

### Phase 4: 統一 UI

1. ⏳ 實現共用的 Sandbox Viewer 元件
2. ⏳ 實現不同 sandbox_type 的 preview renderer
3. ⏳ 實現統一的變更可視化

## 🎯 關鍵洞察

### 收斂一句話

> ✅ **凡是 AI 幫你改東西（不是純讀）的場合，都應該經過 sandbox 這一層。**
>
> 差別只在於：
> - three.js 是「視覺 + code」型 sandbox
> - 書稿是「text」型 sandbox
> - repo 是「branch / patch」型 sandbox
>
> 但對心智空間來說，它們都是同一種「檔案修改宇宙中的安全小宇宙」。

### 設計原則

1. **統一抽象**：所有 sandbox 類型共享相同的核心接口
2. **類型特化**：不同類型可以有自己的特殊方法和驗證邏輯
3. **向後兼容**：現有的直接寫文件方式可以逐步遷移
4. **擴展性**：容易添加新的 sandbox 類型

## 📚 相關文檔

- [Sandbox 系統實作步驟](sandbox-system-implementation-steps.md)
- [Sandbox 系統設計總結](sandbox-system-summary.md)
- [Project + Flow 架構設計](../project-flow/project-flow-architecture.md)
- [Three.js Sandbox 實作規劃](../threejs/threejs-sandbox-implementation-plan.md)


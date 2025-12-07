# Three.js Sandbox 實作步驟詳解

## 快速開始：最小可行版本 (MVP)

### Step 1: 創建 Sandbox 工具基礎結構

#### 1.1 創建目錄和文件

```bash
mkdir -p mindscape-ai-local-core/backend/app/services/tools/threejs_sandbox
```

#### 1.2 創建 `__init__.py`

```python
# mindscape-ai-local-core/backend/app/services/tools/threejs_sandbox/__init__.py

from .threejs_sandbox_tools import (
    ThreeJSSandboxCreateSceneTool,
    ThreeJSSandboxReadSceneTool,
    ThreeJSSandboxUpdateSceneTool,
)

__all__ = [
    "ThreeJSSandboxCreateSceneTool",
    "ThreeJSSandboxReadSceneTool",
    "ThreeJSSandboxUpdateSceneTool",
]
```

#### 1.3 創建 Sandbox 管理器

創建 `sandbox_manager.py` 來處理 sandbox 的基礎操作。

#### 1.4 創建版本管理器

創建 `version_manager.py` 來處理版本相關的操作。

#### 1.5 創建工具實現

創建 `threejs_sandbox_tools.py` 實現所有工具。

### Step 2: 實現核心功能（按優先級）

## 詳細實作步驟

### 步驟 1: Sandbox 管理器 (`sandbox_manager.py`)

**職責：**
- 管理 sandbox 目錄結構
- 處理 slug 生成和驗證
- 維護 sandbox 元數據
- 處理版本符號鏈接

**核心方法：**
```python
class SandboxManager:
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def create_sandbox(self, slug: str, workspace_id: str) -> Path:
        """創建新的 sandbox 目錄結構"""
        pass

    def get_sandbox_path(self, slug: str) -> Path:
        """獲取 sandbox 路徑"""
        pass

    def get_sandbox_metadata(self, slug: str) -> Dict:
        """讀取 sandbox 元數據"""
        pass

    def update_sandbox_metadata(self, slug: str, metadata: Dict):
        """更新 sandbox 元數據"""
        pass
```

### 步驟 2: 版本管理器 (`version_manager.py`)

**職責：**
- 創建新版本
- 管理版本目錄
- 維護版本元數據
- 處理版本差異

**核心方法：**
```python
class VersionManager:
    def __init__(self, sandbox_path: Path):
        self.sandbox_path = sandbox_path

    def create_version(self, base_version: Optional[str] = None) -> str:
        """創建新版本（基於 base_version，如果提供）"""
        pass

    def get_current_version(self) -> str:
        """獲取當前版本號"""
        pass

    def set_current_version(self, version: str):
        """設置當前版本"""
        pass

    def list_versions(self) -> List[str]:
        """列出所有版本"""
        pass

    def get_version_path(self, version: str) -> Path:
        """獲取版本目錄路徑"""
        pass

    def get_version_files(self, version: str) -> Dict[str, str]:
        """讀取版本的所有文件"""
        pass

    def write_version_files(self, version: str, files: Dict[str, str]):
        """寫入版本文件"""
        pass

    def get_version_metadata(self, version: str) -> Dict:
        """讀取版本元數據"""
        pass

    def update_version_metadata(self, version: str, metadata: Dict):
        """更新版本元數據"""
        pass
```

### 步驟 3: 實現工具 (`threejs_sandbox_tools.py`)

#### 3.1 `create_scene` 工具

**功能：**
- 創建新的 sandbox
- 生成初始場景代碼（v1）
- 返回 sandbox 信息和預覽 URL

**接口：**
```python
class ThreeJSSandboxCreateSceneTool(MindscapeTool):
    async def execute(
        self,
        slug: str,
        initial_prompt: str,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        創建新的 Three.js hero sandbox

        Args:
            slug: Sandbox 唯一標識符（例如: "particle-network-001"）
            initial_prompt: 初始場景描述
            workspace_id: 工作空間 ID

        Returns:
            {
                "sandbox_id": "threejs-hero/particle-network-001",
                "slug": "particle-network-001",
                "version": "v1",
                "preview_url": "http://localhost:8888/...",
                "files": {
                    "Component.tsx": "path/to/file"
                }
            }
        """
        pass
```

#### 3.2 `read_scene` 工具

**功能：**
- 讀取指定版本的場景代碼
- 返回所有文件內容

**接口：**
```python
class ThreeJSSandboxReadSceneTool(MindscapeTool):
    async def execute(
        self,
        slug: str,
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        讀取 Three.js hero 場景代碼

        Args:
            slug: Sandbox 唯一標識符
            version: 版本號（例如: "v1", "v2"），如果為 None 則讀取當前版本

        Returns:
            {
                "sandbox_id": "threejs-hero/particle-network-001",
                "version": "v2",
                "files": {
                    "Component.tsx": "完整文件內容...",
                    "index.html": "完整文件內容..."
                },
                "metadata": {
                    "created_at": "...",
                    "modification_prompt": "..."
                }
            }
        """
        pass
```

#### 3.3 `update_scene` 工具

**功能：**
- 基於現有版本進行修改
- 生成新版本
- 自動生成變更摘要

**接口：**
```python
class ThreeJSSandboxUpdateSceneTool(MindscapeTool):
    async def execute(
        self,
        slug: str,
        modification_prompt: str,
        base_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        更新 Three.js hero 場景

        Args:
            slug: Sandbox 唯一標識符
            modification_prompt: 修改指令（例如: "粒子密度減半但保留現在顏色"）
            base_version: 基礎版本（如果為 None 則使用當前版本）

        Returns:
            {
                "sandbox_id": "threejs-hero/particle-network-001",
                "old_version": "v1",
                "new_version": "v2",
                "change_summary": {
                    "type": "modification",
                    "changes": [
                        "粒子數量從 300 減少為 150",
                        "線條透明度略降低"
                    ]
                },
                "preview_url": "http://localhost:8888/..."
            }
        """
        pass
```

### 步驟 4: 整合到工具註冊系統

#### 4.1 創建工具包配置

創建 `threejs-sandbox-pack.yaml`：

```yaml
name: threejs-sandbox-pack
version: 1.0.0
description: Three.js Sandbox management tools

tools:
  - name: threejs_sandbox.create_scene
    type: threejs_sandbox
    class: ThreeJSSandboxCreateSceneTool
    scope: workspace
    category: webfx

  - name: threejs_sandbox.read_scene
    type: threejs_sandbox
    class: ThreeJSSandboxReadSceneTool
    scope: workspace
    category: webfx

  - name: threejs_sandbox.update_scene
    type: threejs_sandbox
    class: ThreeJSSandboxUpdateSceneTool
    scope: workspace
    category: webfx
```

#### 4.2 註冊工具

在工具註冊系統中添加 threejs_sandbox 工具的註冊邏輯。

### 步驟 5: 更新 Playbook

#### 5.1 修改 `threejs_hero_landing.md`

在現有 Playbook 中添加新的階段：

```markdown
### Phase 7: Sandbox 模式（可選）

#### 步驟 7.1: 檢查是否使用 Sandbox
- 詢問用戶：「要創建一個可迭代改進的 sandbox，還是只生成一次性的代碼？」
- 如果用戶選擇 sandbox 模式：
  - 生成 slug（基於描述或使用用戶提供的名稱）
  - 使用 `threejs_sandbox.create_scene()` 創建 sandbox
  - 保存 sandbox_id 到執行上下文

#### 步驟 7.2: 後續迭代（新對話）
- 檢測執行上下文中的 sandbox_id
- 如果存在，詢問：「要修改現有的場景嗎？」
- 如果是，進入迭代模式：
  1. 使用 `threejs_sandbox.read_scene()` 讀取當前版本
  2. 理解用戶的修改指令
  3. 使用 `threejs_sandbox.update_scene()` 應用修改
  4. 顯示變更摘要和 Before/After 對比
```

#### 5.2 創建新的輕量級 Playbook

創建 `threejs_sandbox_iteration.md` 專門用於迭代修改：

```markdown
---
playbook_code: threejs_sandbox_iteration
version: 1.0.0
name: Three.js Sandbox 迭代修改
description: 在現有 Three.js hero 場景上進行迭代式改進
---

## 流程

### Phase 1: 識別 Sandbox
- 從上下文或用戶輸入中獲取 slug
- 驗證 sandbox 是否存在

### Phase 2: 理解修改需求
- 分析用戶的自然語言指令
- 識別要修改的具體元素

### Phase 3: 讀取當前版本
- 使用 `threejs_sandbox.read_scene()` 讀取當前版本代碼
- 分析現有結構

### Phase 4: 生成修改
- 基於當前代碼和修改指令生成新版本
- 確保只修改必要的部分

### Phase 5: 應用修改
- 使用 `threejs_sandbox.update_scene()` 創建新版本
- 生成變更摘要

### Phase 6: 展示結果
- 顯示變更摘要
- 提供 Before/After 對比連結
- 詢問是否繼續修改
```

### 步驟 6: 實現變更摘要生成

創建一個輔助函數來生成變更摘要：

```python
async def generate_change_summary(
    old_files: Dict[str, str],
    new_files: Dict[str, str],
    modification_prompt: str,
    llm_client
) -> Dict[str, Any]:
    """使用 LLM 生成變更摘要"""

    # 計算代碼差異
    diff_text = ""
    for file_path in set(old_files.keys()) | set(new_files.keys()):
        old_content = old_files.get(file_path, "")
        new_content = new_files.get(file_path, "")
        if old_content != new_content:
            diff_text += f"\n\n文件: {file_path}\n"
            diff_text += generate_unified_diff(old_content, new_content)

    prompt = f"""
用戶的修改指令：{modification_prompt}

代碼變更：
{diff_text}

請用簡潔的中文列出這次修改做了什麼，格式如下：
✅ [具體變更描述]
✅ [具體變更描述]

只列出用戶可見或有意義的變更，每個變更一行。
"""

    response = await llm_client.generate(prompt)
    changes = parse_summary_list(response)

    return {
        "type": "modification",
        "prompt": modification_prompt,
        "changes": changes,
        "diff": diff_text
    }
```

## 實作檢查清單

### 基礎架構
- [ ] 創建 `threejs_sandbox` 工具目錄
- [ ] 實現 `SandboxManager` 類
- [ ] 實現 `VersionManager` 類
- [ ] 實現三個核心工具類

### 工具功能
- [ ] `create_scene` - 創建新 sandbox
- [ ] `read_scene` - 讀取場景代碼
- [ ] `update_scene` - 更新場景
- [ ] 變更摘要生成
- [ ] 版本管理（v1, v2, v3...）

### 整合
- [ ] 註冊工具到工具系統
- [ ] 更新 Playbook 支持 sandbox 模式
- [ ] 創建迭代修改 Playbook

### 測試
- [ ] 單元測試：Sandbox 管理器
- [ ] 單元測試：版本管理器
- [ ] 整合測試：創建 → 讀取 → 更新流程
- [ ] 端到端測試：完整 Playbook 執行

## 下一步行動

1. **立即開始：** 實現 Sandbox 管理器和版本管理器
2. **第一週：** 完成三個核心工具的 MVP 版本
3. **第二週：** 整合到 Playbook 並測試
4. **第三週：** 實現變更摘要和優化體驗

## 注意事項

- 保持向後兼容：現有的 `artifacts/` 模式仍可工作
- 安全第一：嚴格驗證路徑，防止目錄遍歷
- 錯誤處理：妥善處理各種邊界情況
- 性能考慮：大量文件時注意性能優化


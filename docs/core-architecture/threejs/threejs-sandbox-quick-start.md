# Three.js Sandbox 快速開始指南

## 🚀 5 分鐘快速開始

### Step 1: 創建目錄結構（1 分鐘）

```bash
cd mindscape-ai-local-core/backend/app/services/tools
mkdir -p threejs_sandbox
cd threejs_sandbox
```

### Step 2: 創建基礎文件（2 分鐘）

創建以下文件（可以直接複製範例代碼）：

1. `__init__.py` - 工具導出
2. `sandbox_manager.py` - Sandbox 管理器
3. `version_manager.py` - 版本管理器
4. `threejs_sandbox_tools.py` - 工具實現

**參考：** [程式碼範例](threejs-sandbox-code-examples.md) 有完整代碼

### Step 3: 配置 Sandbox 基礎路徑（1 分鐘）

在配置文件中添加：

```python
# backend/app/config/sandbox_config.py

from pathlib import Path

SANDBOX_BASE_PATH = Path("data/sandboxes")
THREEJS_SANDBOX_PATH = SANDBOX_BASE_PATH / "threejs-hero"
```

### Step 4: 註冊工具（1 分鐘）

創建或更新工具包配置：

```yaml
# backend/packs/threejs-sandbox-pack.yaml

name: threejs-sandbox-pack
version: 1.0.0

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
```

## 📋 實作優先級

### ✅ 第一階段：基礎功能（必須）

按順序實作：

1. **SandboxManager** - 管理 sandbox 目錄和元數據
2. **VersionManager** - 管理版本（v1, v2, v3...）
3. **create_scene 工具** - 創建新 sandbox
4. **read_scene 工具** - 讀取場景代碼

**目標：** 可以創建和讀取 sandbox

### ⏳ 第二階段：核心功能（重要）

5. **update_scene 工具** - 基於現有版本修改
6. **變更摘要生成** - 用 LLM 分析變更

**目標：** 可以迭代修改場景

### 🔮 第三階段：增強功能（可選）

7. **局部修改** - 代碼塊選擇
8. **Before/After 對比** - 版本對比
9. **預覽服務器** - 自動刷新

## 🎯 MVP 最小實現

如果你只想快速驗證概念，可以先實現最簡版本：

### 最簡 SandboxManager

```python
class SandboxManager:
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def create_sandbox(self, slug: str, workspace_id: str) -> Path:
        sandbox_path = self.base_path / slug
        sandbox_path.mkdir(parents=True, exist_ok=True)
        return sandbox_path
```

### 最簡 VersionManager

```python
class VersionManager:
    def __init__(self, sandbox_path: Path):
        self.versions_path = sandbox_path / "versions"
        self.versions_path.mkdir(exist_ok=True)

    def create_version(self) -> str:
        versions = [d.name for d in self.versions_path.iterdir() if d.is_dir()]
        version_num = len(versions) + 1
        new_version = f"v{version_num}"
        (self.versions_path / new_version).mkdir()
        return new_version
```

### 最簡 create_scene 工具

```python
async def execute(self, slug: str, initial_prompt: str) -> Dict:
    manager = SandboxManager(THREEJS_SANDBOX_PATH)
    sandbox_path = manager.create_sandbox(slug, workspace_id)

    version_manager = VersionManager(sandbox_path)
    version = version_manager.create_version()

    # 暫時使用模板文件
    files = {"Component.tsx": "// TODO: Generate code"}
    version_manager.write_version_files(version, files)

    return {"sandbox_id": f"threejs-hero/{slug}", "version": version}
```

## 🔍 測試你的實現

### 手動測試

```python
# 測試腳本：test_sandbox.py

from pathlib import Path
from threejs_sandbox import SandboxManager, VersionManager

# 測試創建 sandbox
manager = SandboxManager(Path("data/sandboxes/threejs-hero"))
sandbox_path = manager.create_sandbox("test-001", "workspace-123")
print(f"Created: {sandbox_path}")

# 測試創建版本
version_manager = VersionManager(sandbox_path)
v1 = version_manager.create_version()
print(f"Created version: {v1}")

# 測試讀取
files = version_manager.get_version_files(v1)
print(f"Files: {files}")
```

### 運行測試

```bash
cd mindscape-ai-local-core
python -m pytest tests/test_threejs_sandbox.py -v
```

## 📚 參考資源

### 完整文檔

1. **總體規劃**：[Three.js Sandbox 實作規劃](threejs-sandbox-implementation-plan.md)
   - 完整的概念設計和架構

2. **實作步驟**：[Three.js Sandbox 實作步驟](threejs-sandbox-implementation-steps.md)
   - 詳細的實作指南

3. **程式碼範例**：[Three.js Sandbox 程式碼範例](threejs-sandbox-code-examples.md)
   - 完整的程式碼模板

4. **總結文檔**：[Three.js Sandbox 規劃總結](threejs-sandbox-summary.md)
   - 快速總覽

### 現有代碼參考

- **文件系統工具**：`backend/app/services/tools/local_filesystem/filesystem_tools.py`
- **工具基類**：`backend/app/services/tools/base.py`
- **Playbook 範例**：`backend/i18n/playbooks/zh-TW/threejs_hero_landing.md`

## ❓ 常見問題

### Q: 如何整合 LLM 生成代碼？

A: 在 `_generate_initial_scene` 和 `_generate_updated_scene` 方法中調用你的 LLM 服務。

### Q: 預覽 URL 怎麼實現？

A: 可以使用簡單的 HTTP 服務器（如 Python 的 `http.server`）或專用的預覽工具。

### Q: 如何遷移現有的 artifacts？

A: 可以寫一個遷移腳本，將 `artifacts/threejs_hero_landing/{execution_id}/` 轉換為 sandbox 格式。

### Q: Sandbox 和現有的 artifacts 有什麼區別？

A:
- **Artifacts**：每次執行都是獨立的，沒有版本關係
- **Sandbox**：同一個作品的多個版本，可以迭代改進

## 🎯 下一步

1. ✅ 創建基礎目錄結構
2. ✅ 實現 SandboxManager 和 VersionManager
3. ✅ 實現 create_scene 工具
4. ✅ 測試創建和讀取功能
5. ⏳ 實現 update_scene 工具
6. ⏳ 整合 LLM 生成邏輯
7. ⏳ 更新 Playbook

## 💪 開始實作！

現在你已經有：
- ✅ 完整的概念設計
- ✅ 詳細的實作步驟
- ✅ 可直接使用的程式碼範例
- ✅ 清晰的優先級規劃

**開始動手吧！** 從最簡單的 SandboxManager 開始，一步一步構建你的 Sandbox 系統。

有任何問題，隨時參考文檔或查看程式碼範例！


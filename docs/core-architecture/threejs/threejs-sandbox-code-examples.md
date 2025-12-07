# Three.js Sandbox 實作程式碼範例

## 目錄結構示例

```
mindscape-ai-local-core/backend/app/services/tools/threejs_sandbox/
├── __init__.py
├── sandbox_manager.py
├── version_manager.py
├── threejs_sandbox_tools.py
└── utils.py
```

## 1. Sandbox 管理器 (`sandbox_manager.py`)

```python
"""
Sandbox Manager for Three.js Hero scenes
"""
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SandboxManager:
    """管理 Three.js hero sandbox 的創建和元數據"""

    def __init__(self, base_path: Path):
        """
        Args:
            base_path: Sandbox 基礎路徑，例如: data/sandboxes/threejs-hero
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def create_sandbox(
        self,
        slug: str,
        workspace_id: str,
        initial_metadata: Optional[Dict] = None
    ) -> Path:
        """
        創建新的 sandbox 目錄結構

        Args:
            slug: Sandbox 唯一標識符
            workspace_id: 工作空間 ID
            initial_metadata: 初始元數據

        Returns:
            Sandbox 路徑
        """
        sandbox_path = self.base_path / slug
        versions_path = sandbox_path / "versions"

        # 創建目錄結構
        sandbox_path.mkdir(parents=True, exist_ok=True)
        versions_path.mkdir(parents=True, exist_ok=True)

        # 創建初始元數據
        metadata = {
            "sandbox_id": f"threejs-hero/{slug}",
            "slug": slug,
            "workspace_id": workspace_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "current_version": None,
            "versions": [],
            "tags": [],
            **(initial_metadata or {})
        }

        metadata_path = sandbox_path / "sandbox.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Created sandbox: {sandbox_path}")
        return sandbox_path

    def get_sandbox_path(self, slug: str) -> Optional[Path]:
        """獲取 sandbox 路徑，如果不存在則返回 None"""
        sandbox_path = self.base_path / slug
        if sandbox_path.exists() and (sandbox_path / "sandbox.json").exists():
            return sandbox_path
        return None

    def get_sandbox_metadata(self, slug: str) -> Optional[Dict]:
        """讀取 sandbox 元數據"""
        sandbox_path = self.get_sandbox_path(slug)
        if not sandbox_path:
            return None

        metadata_path = sandbox_path / "sandbox.json"
        if not metadata_path.exists():
            return None

        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def update_sandbox_metadata(self, slug: str, updates: Dict):
        """更新 sandbox 元數據"""
        metadata = self.get_sandbox_metadata(slug)
        if not metadata:
            raise ValueError(f"Sandbox not found: {slug}")

        metadata.update(updates)
        metadata["updated_at"] = datetime.utcnow().isoformat()

        sandbox_path = self.get_sandbox_path(slug)
        metadata_path = sandbox_path / "sandbox.json"

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def list_sandboxes(self, workspace_id: Optional[str] = None) -> list[Dict]:
        """列出所有 sandbox（可選按 workspace 過濾）"""
        sandboxes = []

        if not self.base_path.exists():
            return sandboxes

        for item in self.base_path.iterdir():
            if not item.is_dir():
                continue

            metadata = self.get_sandbox_metadata(item.name)
            if not metadata:
                continue

            if workspace_id and metadata.get("workspace_id") != workspace_id:
                continue

            sandboxes.append(metadata)

        return sorted(sandboxes, key=lambda x: x.get("updated_at", ""), reverse=True)
```

## 2. 版本管理器 (`version_manager.py`)

```python
"""
Version Manager for Three.js Hero sandbox versions
"""
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class VersionManager:
    """管理 sandbox 的版本"""

    def __init__(self, sandbox_path: Path):
        """
        Args:
            sandbox_path: Sandbox 根目錄路徑
        """
        self.sandbox_path = sandbox_path
        self.versions_path = sandbox_path / "versions"
        self.versions_path.mkdir(parents=True, exist_ok=True)

    def get_current_version(self) -> Optional[str]:
        """獲取當前版本號"""
        metadata = self._load_sandbox_metadata()
        return metadata.get("current_version")

    def set_current_version(self, version: str):
        """設置當前版本"""
        from .sandbox_manager import SandboxManager

        # 獲取 slug
        slug = self.sandbox_path.name

        # 更新元數據
        manager = SandboxManager(self.sandbox_path.parent)
        manager.update_sandbox_metadata(slug, {"current_version": version})

    def list_versions(self) -> List[str]:
        """列出所有版本號"""
        versions = []
        if not self.versions_path.exists():
            return versions

        for item in self.versions_path.iterdir():
            if item.is_dir() and item.name.startswith("v"):
                versions.append(item.name)

        return sorted(versions, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)

    def create_version(
        self,
        base_version: Optional[str] = None
    ) -> str:
        """
        創建新版本

        Args:
            base_version: 基礎版本號（如果提供，會複製其內容）

        Returns:
            新版本號（例如: "v1", "v2"）
        """
        existing_versions = self.list_versions()

        # 計算新版本號
        if existing_versions:
            last_version = existing_versions[-1]
            version_num = int(last_version[1:]) + 1
        else:
            version_num = 1

        new_version = f"v{version_num}"
        new_version_path = self.versions_path / new_version
        new_version_path.mkdir(parents=True, exist_ok=True)

        # 如果有基礎版本，複製其文件
        if base_version:
            base_version_path = self.versions_path / base_version
            if base_version_path.exists():
                for item in base_version_path.iterdir():
                    if item.is_file():
                        shutil.copy2(item, new_version_path / item.name)

        # 創建版本元數據
        version_metadata = {
            "version": new_version,
            "created_at": datetime.utcnow().isoformat(),
            "base_version": base_version,
            "files": {},
            "change_summary": {}
        }

        metadata_path = new_version_path / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(version_metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Created version: {new_version} (base: {base_version})")
        return new_version

    def get_version_path(self, version: str) -> Path:
        """獲取版本目錄路徑"""
        if version is None:
            version = self.get_current_version() or "v1"

        version_path = self.versions_path / version
        if not version_path.exists():
            raise ValueError(f"Version not found: {version}")

        return version_path

    def get_version_files(self, version: Optional[str] = None) -> Dict[str, str]:
        """讀取版本的所有文件內容"""
        version_path = self.get_version_path(version)
        files = {}

        for item in version_path.iterdir():
            if item.is_file() and item.name != "metadata.json":
                try:
                    with open(item, "r", encoding="utf-8") as f:
                        files[item.name] = f.read()
                except Exception as e:
                    logger.warning(f"Failed to read file {item}: {e}")

        return files

    def write_version_files(self, version: str, files: Dict[str, str]):
        """寫入版本文件"""
        version_path = self.get_version_path(version)

        for file_name, content in files.items():
            file_path = version_path / file_name
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        # 更新版本元數據中的文件列表
        self._update_version_files_metadata(version, list(files.keys()))

    def get_version_metadata(self, version: Optional[str] = None) -> Dict:
        """讀取版本元數據"""
        version_path = self.get_version_path(version)
        metadata_path = version_path / "metadata.json"

        if not metadata_path.exists():
            return {}

        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def update_version_metadata(self, version: str, updates: Dict):
        """更新版本元數據"""
        version_path = self.get_version_path(version)
        metadata_path = version_path / "metadata.json"

        metadata = self.get_version_metadata(version)
        metadata.update(updates)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def _load_sandbox_metadata(self) -> Dict:
        """載入 sandbox 元數據"""
        metadata_path = self.sandbox_path / "sandbox.json"
        if not metadata_path.exists():
            return {}

        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _update_version_files_metadata(self, version: str, file_names: List[str]):
        """更新版本元數據中的文件列表"""
        version_path = self.get_version_path(version)

        files_metadata = {}
        for file_name in file_names:
            file_path = version_path / file_name
            if file_path.exists():
                files_metadata[file_name] = {
                    "path": f"versions/{version}/{file_name}",
                    "size": file_path.stat().st_size
                }

        self.update_version_metadata(version, {"files": files_metadata})
```

## 3. 工具實現 (`threejs_sandbox_tools.py`)

```python
"""
Three.js Sandbox Tools
"""
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema, ToolCategory
from .sandbox_manager import SandboxManager
from .version_manager import VersionManager

logger = logging.getLogger(__name__)


class ThreeJSSandboxCreateSceneTool(MindscapeTool):
    """創建新的 Three.js hero sandbox"""

    def __init__(self, base_directory: str, workspace_id: str):
        self.base_directory = Path(base_directory).expanduser().resolve()
        self.workspace_id = workspace_id

        metadata = ToolMetadata(
            name="threejs_sandbox.create_scene",
            description="創建新的 Three.js hero sandbox 並生成初始場景",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "slug": {
                        "type": "string",
                        "description": "Sandbox 唯一標識符（例如: 'particle-network-001'）"
                    },
                    "initial_prompt": {
                        "type": "string",
                        "description": "初始場景描述或需求"
                    }
                },
                required=["slug", "initial_prompt"]
            ),
            category=ToolCategory.WEBFX,
            source_type="builtin",
            provider="threejs_sandbox",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        slug: str,
        initial_prompt: str
    ) -> Dict[str, Any]:
        """創建新的 sandbox 和初始場景"""
        # 初始化管理器
        sandbox_base = self.base_directory / "threejs-hero"
        manager = SandboxManager(sandbox_base)

        # 檢查 sandbox 是否已存在
        existing = manager.get_sandbox_path(slug)
        if existing:
            raise ValueError(f"Sandbox already exists: {slug}")

        # 創建 sandbox
        sandbox_path = manager.create_sandbox(slug, self.workspace_id)

        # 創建版本管理器
        version_manager = VersionManager(sandbox_path)

        # 創建 v1
        version = version_manager.create_version()

        # 生成初始場景代碼（這裡需要調用 LLM 或使用模板）
        # 暫時返回佔位符，實際需要調用代碼生成邏輯
        initial_files = await self._generate_initial_scene(initial_prompt)

        # 寫入文件
        version_manager.write_version_files(version, initial_files)

        # 設置為當前版本
        version_manager.set_current_version(version)

        # 更新 sandbox 元數據
        manager.update_sandbox_metadata(slug, {
            "current_version": version,
            "versions": [version]
        })

        return {
            "sandbox_id": f"threejs-hero/{slug}",
            "slug": slug,
            "version": version,
            "files": list(initial_files.keys()),
            "preview_url": self._get_preview_url(slug, version)
        }

    async def _generate_initial_scene(self, prompt: str) -> Dict[str, str]:
        """生成初始場景代碼（需要實際實現）"""
        # 這裡應該調用 LLM 生成代碼
        # 暫時返回模板
        return {
            "Component.tsx": "// Generated component code here...",
            "index.html": "<!DOCTYPE html>..."
        }

    def _get_preview_url(self, slug: str, version: str) -> str:
        """獲取預覽 URL"""
        return f"http://localhost:8888/sandboxes/threejs-hero/{slug}/versions/{version}/index.html"


class ThreeJSSandboxReadSceneTool(MindscapeTool):
    """讀取 Three.js hero 場景代碼"""

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory).expanduser().resolve()

        metadata = ToolMetadata(
            name="threejs_sandbox.read_scene",
            description="讀取指定版本的 Three.js hero 場景代碼",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "slug": {
                        "type": "string",
                        "description": "Sandbox 唯一標識符"
                    },
                    "version": {
                        "type": "string",
                        "description": "版本號（例如: 'v1', 'v2'），如果為空則讀取當前版本"
                    }
                },
                required=["slug"]
            ),
            category=ToolCategory.WEBFX,
            source_type="builtin",
            provider="threejs_sandbox",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        slug: str,
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """讀取場景代碼"""
        sandbox_base = self.base_directory / "threejs-hero"
        manager = SandboxManager(sandbox_base)

        sandbox_path = manager.get_sandbox_path(slug)
        if not sandbox_path:
            raise ValueError(f"Sandbox not found: {slug}")

        version_manager = VersionManager(sandbox_path)

        # 如果未指定版本，使用當前版本
        if version is None:
            version = version_manager.get_current_version()
            if not version:
                raise ValueError(f"No current version found for sandbox: {slug}")

        # 讀取文件
        files = version_manager.get_version_files(version)
        metadata = version_manager.get_version_metadata(version)

        return {
            "sandbox_id": f"threejs-hero/{slug}",
            "slug": slug,
            "version": version,
            "files": files,
            "metadata": metadata
        }


class ThreeJSSandboxUpdateSceneTool(MindscapeTool):
    """更新 Three.js hero 場景"""

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory).expanduser().resolve()

        metadata = ToolMetadata(
            name="threejs_sandbox.update_scene",
            description="基於現有版本更新 Three.js hero 場景",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "slug": {
                        "type": "string",
                        "description": "Sandbox 唯一標識符"
                    },
                    "modification_prompt": {
                        "type": "string",
                        "description": "修改指令（例如: '粒子密度減半但保留現在顏色'）"
                    },
                    "base_version": {
                        "type": "string",
                        "description": "基礎版本（如果為空則使用當前版本）"
                    }
                },
                required=["slug", "modification_prompt"]
            ),
            category=ToolCategory.WEBFX,
            source_type="builtin",
            provider="threejs_sandbox",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        slug: str,
        modification_prompt: str,
        base_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """更新場景"""
        sandbox_base = self.base_directory / "threejs-hero"
        manager = SandboxManager(sandbox_base)

        sandbox_path = manager.get_sandbox_path(slug)
        if not sandbox_path:
            raise ValueError(f"Sandbox not found: {slug}")

        version_manager = VersionManager(sandbox_path)

        # 確定基礎版本
        if base_version is None:
            base_version = version_manager.get_current_version()
            if not base_version:
                raise ValueError(f"No current version found for sandbox: {slug}")

        # 讀取基礎版本文件
        old_files = version_manager.get_version_files(base_version)

        # 生成新版本
        new_version = version_manager.create_version(base_version=base_version)

        # 生成修改後的代碼（需要實際實現，調用 LLM）
        new_files = await self._generate_updated_scene(
            old_files,
            modification_prompt
        )

        # 寫入新版本
        version_manager.write_version_files(new_version, new_files)

        # 生成變更摘要
        change_summary = await self._generate_change_summary(
            old_files,
            new_files,
            modification_prompt
        )

        # 更新版本元數據
        version_manager.update_version_metadata(new_version, {
            "modification_prompt": modification_prompt,
            "change_summary": change_summary
        })

        # 設置為當前版本
        version_manager.set_current_version(new_version)

        # 更新 sandbox 元數據
        metadata = manager.get_sandbox_metadata(slug)
        versions = metadata.get("versions", [])
        if new_version not in versions:
            versions.append(new_version)
        manager.update_sandbox_metadata(slug, {
            "current_version": new_version,
            "versions": versions
        })

        return {
            "sandbox_id": f"threejs-hero/{slug}",
            "old_version": base_version,
            "new_version": new_version,
            "change_summary": change_summary,
            "preview_url": self._get_preview_url(slug, new_version)
        }

    async def _generate_updated_scene(
        self,
        old_files: Dict[str, str],
        modification_prompt: str
    ) -> Dict[str, str]:
        """生成修改後的場景代碼（需要實際實現）"""
        # 這裡應該調用 LLM 分析現有代碼並生成修改後的版本
        # 暫時返回原文件（實際需要實現）
        return old_files

    async def _generate_change_summary(
        self,
        old_files: Dict[str, str],
        new_files: Dict[str, str],
        modification_prompt: str
    ) -> Dict[str, Any]:
        """生成變更摘要（需要實際實現）"""
        # 這裡應該調用 LLM 分析差異並生成摘要
        return {
            "type": "modification",
            "prompt": modification_prompt,
            "changes": [
                "變更摘要需要通過 LLM 生成"
            ]
        }

    def _get_preview_url(self, slug: str, version: str) -> str:
        """獲取預覽 URL"""
        return f"http://localhost:8888/sandboxes/threejs-hero/{slug}/versions/{version}/index.html"
```

## 4. 工具初始化 (`__init__.py`)

```python
"""
Three.js Sandbox Tools
"""
from .threejs_sandbox_tools import (
    ThreeJSSandboxCreateSceneTool,
    ThreeJSSandboxReadSceneTool,
    ThreeJSSandboxUpdateSceneTool,
)
from .sandbox_manager import SandboxManager
from .version_manager import VersionManager

__all__ = [
    "ThreeJSSandboxCreateSceneTool",
    "ThreeJSSandboxReadSceneTool",
    "ThreeJSSandboxUpdateSceneTool",
    "SandboxManager",
    "VersionManager",
]
```

## 使用範例

### 創建新 Sandbox

```python
tool = ThreeJSSandboxCreateSceneTool(
    base_directory="/path/to/data/sandboxes",
    workspace_id="workspace-123"
)

result = await tool.execute(
    slug="particle-network-001",
    initial_prompt="生成一個動態粒子網絡的 Three.js hero 區塊"
)

print(result)
# {
#     "sandbox_id": "threejs-hero/particle-network-001",
#     "slug": "particle-network-001",
#     "version": "v1",
#     "files": ["Component.tsx", "index.html"],
#     "preview_url": "http://localhost:8888/..."
# }
```

### 讀取場景

```python
tool = ThreeJSSandboxReadSceneTool(
    base_directory="/path/to/data/sandboxes"
)

result = await tool.execute(
    slug="particle-network-001",
    version="v1"  # 可選，不提供則讀取當前版本
)

print(result["files"]["Component.tsx"])
```

### 更新場景

```python
tool = ThreeJSSandboxUpdateSceneTool(
    base_directory="/path/to/data/sandboxes"
)

result = await tool.execute(
    slug="particle-network-001",
    modification_prompt="粒子密度減半但保留現在顏色"
)

print(result["change_summary"])
# {
#     "type": "modification",
#     "changes": [
#         "粒子數量從 300 減少為 150",
#         "線條透明度略降低"
#     ]
# }
```

## 下一步

這些是基礎的程式碼結構。實際實作時還需要：

1. **整合 LLM 調用**：實現 `_generate_initial_scene` 和 `_generate_updated_scene`
2. **實現變更摘要生成**：調用 LLM 分析代碼差異
3. **預覽服務器**：實現預覽 URL 對應的實際服務
4. **工具註冊**：將工具註冊到系統中
5. **Playbook 更新**：更新現有 Playbook 使用新工具


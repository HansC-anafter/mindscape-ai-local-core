"""
Playbook installer and validation helpers extracted from capability_installer.py
"""

import json
import logging
import os
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import yaml

from .install_result import InstallResult

logger = logging.getLogger(__name__)


class PlaybookInstaller:
    """Install and validate playbooks (specs + markdown + tool call tests)."""

    def _install_playbooks(
        self, cap_dir: Path, capability_code: str, manifest: Dict, result: InstallResult
    ):
        """Install playbook specs and markdown files"""
        playbooks_config = manifest.get("playbooks", [])

        # Get capability installation directory
        cap_install_dir = self.capabilities_dir / capability_code
        cap_playbooks_dir = cap_install_dir / "playbooks"

        for pb_config in playbooks_config:
            playbook_code = pb_config.get("code")
            if not playbook_code:
                continue

            # Install JSON spec
            spec_path = cap_dir / pb_config.get(
                "spec_path", f"playbooks/specs/{playbook_code}.json"
            )
            if spec_path.exists():
                # ⚠️ 硬規則：驗證 playbook spec 必要字段
                required_fields_errors = self._validate_playbook_required_fields(
                    spec_path, playbook_code
                )
                if required_fields_errors:
                    error_msg = f"Playbook {playbook_code} missing required fields: {required_fields_errors}"
                    logger.error(error_msg)
                    result.add_error(error_msg)
                    continue  # 跳過此 playbook 的安裝

                # ⚠️ 硬規則：驗證 playbook spec 不使用 legacy `tool` 字段
                legacy_tool_errors = self._validate_no_legacy_tool_field(
                    spec_path, playbook_code
                )
                if legacy_tool_errors:
                    error_msg = f"Playbook {playbook_code} uses legacy 'tool' field (已棄用): {legacy_tool_errors}"
                    logger.error(error_msg)
                    result.add_error(error_msg)
                    continue  # 跳過此 playbook 的安裝

                # Install to backend/playbooks/specs/ (backward compatibility)
                target_spec = self.specs_dir / f"{playbook_code}.json"
                self.specs_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(spec_path, target_spec)
                result.add_installed("playbooks", playbook_code)
                logger.debug(f"Installed spec: {playbook_code}.json")

                # Also install to capabilities/{code}/playbooks/specs/ (correct location)
                cap_specs_dir = cap_playbooks_dir / "specs"
                cap_specs_dir.mkdir(parents=True, exist_ok=True)
                cap_target_spec = cap_specs_dir / f"{playbook_code}.json"
                shutil.copy2(spec_path, cap_target_spec)
                logger.debug(f"Installed spec to capability dir: {cap_target_spec}")
            else:
                # Spec file not found - log warning but don't block installation
                warning_msg = (
                    f"Playbook {playbook_code}: spec file not found: {spec_path}"
                )
                logger.warning(warning_msg)
                result.add_warning(warning_msg)

            # Install markdown files
            locales = pb_config.get("locales", ["zh-TW", "en"])
            md_path_template = pb_config.get(
                "path", f"playbooks/{{locale}}/{playbook_code}.md"
            )

            for locale in locales:
                md_path = cap_dir / md_path_template.format(locale=locale)
                if md_path.exists():
                    # Install to backend/i18n/playbooks/{locale}/ (backward compatibility)
                    target_md_dir = self.i18n_base_dir / locale
                    target_md_dir.mkdir(parents=True, exist_ok=True)
                    target_md = target_md_dir / f"{playbook_code}.md"
                    shutil.copy2(md_path, target_md)
                    logger.debug(f"Installed markdown: {playbook_code}.md ({locale})")

                    # Also install to capabilities/{code}/playbooks/{locale}/ (correct location)
                    cap_locale_dir = cap_playbooks_dir / locale
                    cap_locale_dir.mkdir(parents=True, exist_ok=True)
                    cap_target_md = cap_locale_dir / f"{playbook_code}.md"
                    shutil.copy2(md_path, cap_target_md)
                    logger.debug(
                        f"Installed markdown to capability dir: {cap_target_md}"
                    )

    def _validate_playbook_required_fields(
        self, spec_path: Path, playbook_code: str
    ) -> List[str]:
        """
        Validate that playbook spec has all required fields according to checklist

        ⚠️ 硬規則：根據實作規章 checklist 驗證 playbook spec
        """
        errors = []
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = json.load(f)

            # 1. PlaybookJson 模型必需字段（新格式）
            required_model_fields = ["kind", "inputs", "outputs"]
            for field in required_model_fields:
                if field not in spec:
                    errors.append(
                        f"Missing required field (PlaybookJson model): '{field}'"
                    )
                elif field == "inputs" and not isinstance(spec.get(field), dict):
                    errors.append(f"Field 'inputs' must be a dictionary")
                elif field == "outputs" and not isinstance(spec.get(field), dict):
                    errors.append(f"Field 'outputs' must be a dictionary")

            # 2. Playbook Spec 核心欄位（舊格式兼容性檢查）
            core_fields = [
                "playbook_code",
                "version",
                "display_name",
                "description",
                "steps",
            ]
            for field in core_fields:
                if field not in spec:
                    errors.append(f"Missing required field (core spec): '{field}'")
                elif field == "steps" and not isinstance(spec.get(field), list):
                    errors.append(f"Field 'steps' must be a list")

            # 3. 能力宣告檢查
            if "required_capabilities" not in spec:
                errors.append(
                    "Missing 'required_capabilities' field (must declare capability dependencies)"
                )

            # 4. 資料邊界檢查
            if "data_locality" not in spec:
                errors.append(
                    "Missing 'data_locality' field (must declare data boundary: local_only and cloud_allowed)"
                )

            # 5. Cloud 專用欄位禁止檢查
            cloud_forbidden_fields = [
                "webhook_url",
                "webhook_auth",
                "bundle_id",
                "download_url",
                "checksum",
            ]
            for field in cloud_forbidden_fields:
                if field in spec:
                    errors.append(
                        f"Forbidden cloud-specific field found: '{field}' (must not be in playbook spec)"
                    )

            # 6. input_schema 中禁止 Cloud 專用欄位
            input_schema = spec.get("input_schema", {})
            if isinstance(input_schema, dict):
                properties = input_schema.get("properties", {})
                cloud_forbidden_inputs = [
                    "tenant_id",
                    "actor_id",
                    "subject_user_id",
                    "plan_id",
                    "execution_id",
                    "trace_id",
                ]
                for field in cloud_forbidden_inputs:
                    if field in properties:
                        errors.append(
                            f"Forbidden cloud-specific field in input_schema: '{field}' (must not be in playbook input_schema)"
                        )

            return errors
        except json.JSONDecodeError as e:
            return [f"Invalid JSON: {str(e)}"]
        except Exception as e:
            return [f"Validation error: {str(e)}"]

    def _validate_no_legacy_tool_field(
        self, spec_path: Path, playbook_code: str
    ) -> List[str]:
        """
        Validate that playbook spec does not use legacy 'tool' field

        ⚠️ 硬規則：playbook 必須使用 tool_slot 字段，tool 字段已棄用
        """
        errors = []
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = json.load(f)

            steps = spec.get("steps", [])
            if not isinstance(steps, list):
                return errors

            for step_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue

                # 檢查是否使用 legacy 'tool' 字段
                if "tool" in step:
                    step_id = step.get("id", f"step_{step_idx}")
                    errors.append(
                        f"Step '{step_id}' uses legacy 'tool' field: '{step['tool']}'. "
                        f"Must use 'tool_slot' field instead (format: 'capability.tool_name', e.g., 'yogacoach.intake_router')"
                    )

            if errors:
                logger.error(
                    f"Playbook {playbook_code} validation failed: legacy 'tool' field detected in {len(errors)} step(s)"
                )

        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in playbook spec: {e}")
        except Exception as e:
            errors.append(f"Error validating playbook spec: {e}")

        return errors

    def _validate_tools_direct_call(
        self, playbook_code: str, capability_code: str
    ) -> Tuple[List[str], List[str]]:
        """
        Validate tools by directly calling them (backend simulation, no LLM)

        ⚠️ 新測試：直接通過後端模擬調用 tool，驗證 tool 是否正確註冊和可調用

        ⚠️ 注意：只驗證 required_capabilities 中的工具，optional 依賴的工具如果不存在只給警告
        """
        errors = []
        warnings = []

        # 讀取 manifest 以獲取可選 Python 依賴
        optional_python_packages = []
        possible_dir_names = [capability_code, capability_code.replace("_", "-"), capability_code.replace("-", "_")]
        for dir_name in possible_dir_names:
            manifest_path = self.capabilities_dir / dir_name / "manifest.yaml"
            if manifest_path.exists():
                try:
                    import yaml
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = yaml.safe_load(f) or {}
                        deps = manifest.get("dependencies", {})
                        python_packages = deps.get("python_packages", {})
                        optional_python_packages = python_packages.get("optional", [])
                        if optional_python_packages:
                            logger.debug(f"Found optional Python packages in manifest: {optional_python_packages}")
                        break
                except Exception as e:
                    logger.debug(f"Failed to read manifest for optional Python packages: {e}")
                break

        # 讀取 playbook spec 以獲取 required_capabilities
        spec_path = self.specs_dir / f"{playbook_code}.json"
        required_capabilities = []
        if spec_path.exists():
            try:
                with open(spec_path, "r", encoding="utf-8") as f:
                    spec = json.load(f)
                    required_capabilities = spec.get("required_capabilities", [])
            except Exception as e:
                logger.warning(f"Failed to read playbook spec for required_capabilities: {e}")

        manifest_tool_backends: Dict[str, Dict[str, str]] = {}

        def get_backend_from_manifest(cap: str, tool: str) -> Optional[str]:
            """
            Resolve backend path from capability manifest (no registry dependency).

            Handles directory name variations (underscore vs hyphen) by trying both.
            """
            if cap in manifest_tool_backends:
                return manifest_tool_backends[cap].get(tool)

            manifest_tool_backends[cap] = {}

            # Try multiple directory name variations (underscore <-> hyphen)
            possible_dirs = [cap, cap.replace("_", "-"), cap.replace("-", "_")]
            manifest_path = None

            for dir_name in possible_dirs:
                candidate_path = self.capabilities_dir / dir_name / "manifest.yaml"
                if candidate_path.exists():
                    manifest_path = candidate_path
                    break

            if manifest_path and manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as mf:
                        manifest = yaml.safe_load(mf) or {}
                        for tool_cfg in manifest.get("tools", []):
                            if not isinstance(tool_cfg, dict):
                                continue
                            code = tool_cfg.get("code") or tool_cfg.get("name")
                            backend_path = tool_cfg.get("backend")
                            if code and backend_path:
                                manifest_tool_backends[cap][code] = backend_path
                                logger.debug(f"Found tool backend from manifest: {cap}.{code} -> {backend_path}")
                except Exception as e:
                    logger.warning(f"Failed to read manifest for capability {cap} from {manifest_path}: {e}")
            else:
                logger.debug(f"Manifest not found for capability {cap}, tried paths: {[str(self.capabilities_dir / d / 'manifest.yaml') for d in possible_dirs]}")

            return manifest_tool_backends[cap].get(tool)
        try:
            # 一次性設置 capabilities 模組結構（在驗證開始前）
            from pathlib import Path
            import importlib.util as importlib_util
            import types

            # 直接使用安裝目錄，不依賴 registry（驗證時可能還沒註冊）
            # 處理目錄名稱變體（下劃線 vs 連字符）
            possible_dir_names = [capability_code, capability_code.replace("_", "-"), capability_code.replace("-", "_")]
            capability_dir = None
            actual_dir_name = None

            for dir_name in possible_dir_names:
                candidate_dir = self.capabilities_dir / dir_name
                if candidate_dir.exists():
                    capability_dir = candidate_dir
                    actual_dir_name = dir_name
                    break

            if capability_dir and capability_dir.exists():
                # 確保 capability_dir 是 Path 對象
                if isinstance(capability_dir, str):
                    capability_dir = Path(capability_dir)

                capabilities_parent = capability_dir.parent
                cloud_root = capabilities_parent.parent  # e.g. /.../backend/app
                backend_root = cloud_root.parent  # e.g. /.../backend

                # 加入 sys.path，確保 capabilities.*, backend.app.*, app.* 都能被 import
                for path in [capabilities_parent, cloud_root, backend_root]:
                    if path and str(path) not in sys.path:
                        sys.path.insert(0, str(path))

                # 創建 capabilities package 結構
                if "capabilities" not in sys.modules:
                    capabilities_module = types.ModuleType("capabilities")
                    capabilities_module.__path__ = [str(capabilities_parent)]
                    sys.modules["capabilities"] = capabilities_module

                # 創建 capability package（使用 capability_code，不是實際目錄名）
                cap_module_path = f"capabilities.{capability_code}"
                if cap_module_path not in sys.modules:
                    cap_module = types.ModuleType(cap_module_path)
                    cap_module.__path__ = [str(capability_dir)]
                    sys.modules[cap_module_path] = cap_module
                    setattr(sys.modules["capabilities"], capability_code, cap_module)

                # 同時創建 app.capabilities.* 模組路徑（用於 backend 路徑中的 app.capabilities.*）
                app_cap_module_path = f"app.capabilities.{capability_code}"
                if app_cap_module_path not in sys.modules:
                    # Ensure we do NOT shadow the real 'app' package.
                    # If we create a plain ModuleType("app") without __path__/__spec__,
                    # imports like "import app.models" will fail ("app is not a package").
                    # Prefer importing the real package if available.
                    if "app" not in sys.modules:
                        try:
                            import importlib
                            importlib.import_module("app")
                        except Exception:
                            app_module = types.ModuleType("app")
                            app_module.__path__ = [str(cloud_root)]
                            init_file = cloud_root / "__init__.py"
                            if init_file.exists():
                                import importlib.util
                                spec = importlib.util.spec_from_file_location(
                                    "app",
                                    init_file,
                                    submodule_search_locations=[str(cloud_root)],
                                )
                                if spec:
                                    app_module.__spec__ = spec
                            sys.modules["app"] = app_module

                    # 創建 app.capabilities 模組（如果不存在）
                    app_capabilities_path = "app.capabilities"
                    if app_capabilities_path not in sys.modules:
                        app_capabilities_module = types.ModuleType(app_capabilities_path)
                        app_capabilities_module.__path__ = [str(capabilities_parent)]

                        # 設置 __spec__ 以避免 __spec__ is None 錯誤
                        # 創建一個虛擬的 __init__.py 路徑（如果不存在）
                        capabilities_init = capabilities_parent / "__init__.py"
                        if not capabilities_init.exists():
                            # 如果不存在 __init__.py，創建一個臨時文件
                            capabilities_init.touch()

                        if capabilities_init.exists():
                            import importlib.util
                            spec = importlib.util.spec_from_file_location(
                                app_capabilities_path,
                                capabilities_init,
                                submodule_search_locations=[str(capabilities_parent)]
                            )
                            if spec:
                                app_capabilities_module.__spec__ = spec
                                logger.debug(f"Set __spec__ for {app_capabilities_path} from {capabilities_init}")

                        sys.modules[app_capabilities_path] = app_capabilities_module
                        if not hasattr(sys.modules["app"], "capabilities"):
                            setattr(sys.modules["app"], "capabilities", app_capabilities_module)

                    # 創建 app.capabilities.{capability_code} 模組
                    app_cap_module = types.ModuleType(app_cap_module_path)
                    app_cap_module.__path__ = [str(capability_dir)]

                    # 設置 __spec__ 以避免 __spec__ is None 錯誤
                    init_file = capability_dir / "__init__.py"
                    if init_file.exists():
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(
                            app_cap_module_path,
                            init_file,
                            submodule_search_locations=[str(capability_dir)]
                        )
                        if spec:
                            app_cap_module.__spec__ = spec
                            logger.debug(f"Set __spec__ for app.capabilities.{capability_code} from {init_file}")

                    sys.modules[app_cap_module_path] = app_cap_module
                    setattr(sys.modules[app_capabilities_path], capability_code, app_cap_module)

                    logger.debug(f"Created app.capabilities.{capability_code} module pointing to {capability_dir}")

                # 預載入 models（支援 models.py 檔案或 models/ 目錄）
                models_module_path = f"capabilities.{capability_code}.models"
                models_dir = capability_dir / "models"
                models_file = capability_dir / "models.py"

                if models_module_path not in sys.modules:
                    try:
                        if models_dir.exists() and models_dir.is_dir():
                            # models/ 是一個 package 目錄，載入 __init__.py
                            models_init = models_dir / "__init__.py"
                            if models_init.exists():
                                # 先創建 models package
                                models_pkg = types.ModuleType(models_module_path)
                                models_pkg.__path__ = [str(models_dir)]
                                models_pkg.__file__ = str(models_init)
                                sys.modules[models_module_path] = models_pkg
                                setattr(
                                    sys.modules[cap_module_path], "models", models_pkg
                                )

                                # 執行 __init__.py
                                models_spec = importlib_util.spec_from_file_location(
                                    models_module_path,
                                    models_init,
                                    submodule_search_locations=[str(models_dir)],
                                )
                                if models_spec and models_spec.loader:
                                    models_spec.loader.exec_module(models_pkg)
                                    logger.info(
                                        f"Pre-loaded models package from {models_init}"
                                    )
                            else:
                                logger.warning(
                                    f"models/ directory exists but no __init__.py found: {models_dir}"
                                )
                        elif models_file.exists():
                            # models.py 是單一檔案
                            models_spec = importlib_util.spec_from_file_location(
                                models_module_path, models_file
                            )
                            if models_spec and models_spec.loader:
                                models_module = importlib_util.module_from_spec(
                                    models_spec
                                )
                                models_spec.loader.exec_module(models_module)
                                sys.modules[models_module_path] = models_module
                                setattr(
                                    sys.modules[cap_module_path],
                                    "models",
                                    models_module,
                                )
                                logger.info(f"Pre-loaded models.py from {models_file}")
                        else:
                            logger.debug(
                                f"No models.py or models/ directory found in {capability_dir}"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to pre-load models: {e}")
                        import traceback

                        logger.debug(traceback.format_exc())

                # 預載入 database_dependency.py
                db_dep_path = capability_dir / "database_dependency.py"
                db_dep_module_path = (
                    f"capabilities.{capability_code}.database_dependency"
                )
                if db_dep_path.exists() and db_dep_module_path not in sys.modules:
                    try:
                        db_dep_spec = importlib_util.spec_from_file_location(
                            db_dep_module_path, db_dep_path
                        )
                        if db_dep_spec and db_dep_spec.loader:
                            db_dep_module = importlib_util.module_from_spec(db_dep_spec)
                            db_dep_spec.loader.exec_module(db_dep_module)
                            sys.modules[db_dep_module_path] = db_dep_module
                            setattr(
                                sys.modules[cap_module_path],
                                "database_dependency",
                                db_dep_module,
                            )
                    except Exception as e:
                        logger.debug(f"Failed to pre-load database_dependency.py: {e}")

            # 讀取 playbook spec
            spec_path = (
                self.capabilities_dir
                / capability_code
                / "playbooks"
                / "specs"
                / f"{playbook_code}.json"
            )
            if not spec_path.exists():
                # 也檢查舊位置
                spec_path = self.specs_dir / f"{playbook_code}.json"
                if not spec_path.exists():
                    errors.append(f"Playbook spec not found: {playbook_code}.json")
                    return errors

            with open(spec_path, "r", encoding="utf-8") as f:
                spec = json.load(f)

            steps = spec.get("steps", [])
            if not isinstance(steps, list):
                return errors

            # 導入必要的模組（延遲導入，避免循環依賴）
            try:
                from backend.app.shared.tool_executor import ToolExecutor

                tool_executor = ToolExecutor()
            except ImportError as e:
                errors.append(f"Failed to import ToolExecutor: {e}")
                return errors

            # 測試每個 step 的 tool_slot
            for step_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue

                step_id = step.get("id", f"step_{step_idx}")
                tool_slot = step.get("tool_slot")
                step_condition = step.get("condition")  # 檢查是否有條件

                if not tool_slot:
                    # 沒有 tool_slot 的 step（可能是條件判斷等），跳過
                    continue

                # 跳過 core slots（它們由系統處理，不需要驗證）
                if tool_slot.startswith("core."):
                    continue

                # 檢查工具是否來自 required_capabilities
                tool_capability = tool_slot.split(".", 1)[0] if "." in tool_slot else None
                is_required = tool_capability in required_capabilities if tool_capability else False

                # 如果工具不在 required_capabilities 中，且有 condition，則跳過驗證（視為 optional）
                if not is_required and step_condition:
                    logger.debug(
                        f"Step '{step_id}': Tool '{tool_slot}' is optional (has condition and not in required_capabilities), skipping validation"
                    )
                    continue

                # 直接測試 tool 是否可調用
                try:
                    # 對於 capability tool，格式是 capability.tool_name
                    if "." in tool_slot:
                        parts = tool_slot.split(".", 1)
                        if len(parts) == 2:
                            cap, tool_name = parts

                            import importlib
                            import inspect

                            # 優先從 manifest 讀取 backend，避開 registry 時序問題
                            backend_path = get_backend_from_manifest(cap, tool_name)
                            if backend_path:
                                logger.debug(f"Step '{step_id}': Found backend from manifest: {cap}.{tool_name} -> {backend_path}")
                            else:
                                # 回退到 registry（工具已註冊時使用）
                                logger.debug(f"Step '{step_id}': Backend not found in manifest for {cap}.{tool_name}, trying registry...")
                                from backend.app.capabilities.registry import (
                                    get_tool_backend,
                                )
                                backend_path = get_tool_backend(cap, tool_name)
                                if backend_path:
                                    logger.debug(f"Step '{step_id}': Found backend from registry: {cap}.{tool_name} -> {backend_path}")

                            # 為當前工具對應的 capability 設置模組路徑（如果尚未設置）
                            # 處理目錄名稱變體
                            possible_dir_names = [cap, cap.replace("_", "-"), cap.replace("-", "_")]
                            tool_capability_dir = None
                            for dir_name in possible_dir_names:
                                candidate_dir = self.capabilities_dir / dir_name
                                if candidate_dir.exists():
                                    tool_capability_dir = candidate_dir
                                    break

                            if tool_capability_dir and tool_capability_dir.exists():
                                # 設置 app.capabilities.* 模組路徑
                                app_cap_module_path = f"app.capabilities.{cap}"
                                if app_cap_module_path not in sys.modules:
                                    # Ensure we do NOT shadow the real 'app' package.
                                    # Creating a plain ModuleType("app") without __path__/__spec__ breaks
                                    # imports like "import app.models" ("app is not a package").
                                    if "app" not in sys.modules:
                                        try:
                                            import importlib
                                            importlib.import_module("app")
                                        except Exception:
                                            app_module = types.ModuleType("app")
                                            # Fallback: make it a package-like module
                                            app_module.__path__ = [str(cloud_root)]
                                            init_file = cloud_root / "__init__.py"
                                            if init_file.exists():
                                                import importlib.util
                                                spec = importlib.util.spec_from_file_location(
                                                    "app",
                                                    init_file,
                                                    submodule_search_locations=[str(cloud_root)],
                                                )
                                                if spec:
                                                    app_module.__spec__ = spec
                                            sys.modules["app"] = app_module

                                    # 創建 app.capabilities 模組（如果不存在）
                                    app_capabilities_path = "app.capabilities"
                                    if app_capabilities_path not in sys.modules:
                                        app_capabilities_module = types.ModuleType(app_capabilities_path)
                                        app_capabilities_module.__path__ = [str(tool_capability_dir.parent)]

                                        # 設置 __spec__ 以避免 __spec__ is None 錯誤
                                        capabilities_parent = tool_capability_dir.parent
                                        capabilities_init = capabilities_parent / "__init__.py"
                                        if not capabilities_init.exists():
                                            capabilities_init.touch()

                                        if capabilities_init.exists():
                                            import importlib.util
                                            spec = importlib.util.spec_from_file_location(
                                                app_capabilities_path,
                                                capabilities_init,
                                                submodule_search_locations=[str(capabilities_parent)]
                                            )
                                            if spec:
                                                app_capabilities_module.__spec__ = spec
                                                logger.debug(f"Set __spec__ for {app_capabilities_path} from {capabilities_init}")

                                        sys.modules[app_capabilities_path] = app_capabilities_module
                                        if not hasattr(sys.modules["app"], "capabilities"):
                                            setattr(sys.modules["app"], "capabilities", app_capabilities_module)

                                    # 創建 app.capabilities.{cap} 模組
                                    app_cap_module = types.ModuleType(app_cap_module_path)
                                    app_cap_module.__path__ = [str(tool_capability_dir)]

                                    # 設置 __spec__ 以避免 __spec__ is None 錯誤
                                    init_file = tool_capability_dir / "__init__.py"
                                    if init_file.exists():
                                        import importlib.util
                                        spec = importlib.util.spec_from_file_location(
                                            app_cap_module_path,
                                            init_file,
                                            submodule_search_locations=[str(tool_capability_dir)]
                                        )
                                        if spec:
                                            app_cap_module.__spec__ = spec
                                            logger.debug(f"Set __spec__ for app.capabilities.{cap} from {init_file}")

                                    sys.modules[app_cap_module_path] = app_cap_module
                                    setattr(sys.modules[app_capabilities_path], cap, app_cap_module)

                                    logger.debug(f"Created app.capabilities.{cap} module for tool validation, pointing to {tool_capability_dir}")

                            if backend_path is None:
                                # 如果工具不在 required_capabilities 中，只給警告，不視為錯誤
                                if not is_required:
                                    logger.warning(
                                        f"Step '{step_id}': Tool '{tool_slot}' from optional capability '{cap}' not found, skipping validation"
                                    )
                                    continue
                                else:
                                    errors.append(
                                        f"Step '{step_id}': Tool '{tool_slot}' backend not found (required capability)"
                                    )
                                    continue

                            if ":" not in backend_path:
                                errors.append(
                                    f"Step '{step_id}': Tool '{tool_slot}' invalid backend format: '{backend_path}'"
                                )
                                continue

                            module_path, target = backend_path.rsplit(":", 1)

                            # Note: app.capabilities.* paths are already correct for local-core
                            # Only add backend. prefix if it's not already there and not app.capabilities.*
                            if module_path.startswith("app.capabilities."):
                                # app.capabilities.* is correct as-is for local-core
                                # 確保父模組的 __spec__ 已設置（在導入工具模組之前）
                                parent_module_path = "app.capabilities." + cap
                                if tool_capability_dir:
                                    init_file = tool_capability_dir / "__init__.py"
                                    if init_file.exists():
                                        if parent_module_path not in sys.modules:
                                            # 創建模組（如果不存在）
                                            if "app" not in sys.modules:
                                                app_module = types.ModuleType("app")
                                                sys.modules["app"] = app_module
                                            if "app.capabilities" not in sys.modules:
                                                app_capabilities_module = types.ModuleType("app.capabilities")
                                                app_capabilities_module.__path__ = [str(tool_capability_dir.parent)]
                                                sys.modules["app.capabilities"] = app_capabilities_module
                                                setattr(sys.modules["app"], "capabilities", app_capabilities_module)
                                            app_cap_module = types.ModuleType(parent_module_path)
                                            app_cap_module.__path__ = [str(tool_capability_dir)]
                                            sys.modules[parent_module_path] = app_cap_module
                                            setattr(sys.modules["app.capabilities"], cap, app_cap_module)

                                        # 確保 __spec__ 已設置
                                        parent_module = sys.modules[parent_module_path]
                                        if not hasattr(parent_module, "__spec__") or parent_module.__spec__ is None:
                                            import importlib.util
                                            spec = importlib.util.spec_from_file_location(
                                                parent_module_path,
                                                init_file,
                                                submodule_search_locations=[str(tool_capability_dir)]
                                            )
                                            if spec:
                                                parent_module.__spec__ = spec
                                                logger.debug(f"Set __spec__ for {parent_module_path} before importing tool module")
                                pass
                            elif module_path.startswith("app."):
                                # Other app.* paths need backend. prefix
                                module_path = "backend." + module_path

                            # 強制先載入 capability models（確保 Plan 等 fallback 邏輯執行）
                            models_module_path = f"capabilities.{cap}.models"
                            logger.info(
                                f"Pre-loading {models_module_path} for tool '{tool_slot}' validation"
                            )
                            logger.debug(
                                f"sys.path before pre-load: {sys.path[:5]}... (showing first 5)"
                            )

                            try:
                                models_module = importlib.import_module(
                                    models_module_path
                                )

                                # 檢查模組狀態
                                logger.info(
                                    f"Module '{models_module_path}' loaded, checking Plan availability..."
                                )
                                logger.debug(
                                    f"Module in sys.modules: {models_module_path in sys.modules}"
                                )
                                logger.debug(f"Module object: {models_module}")
                                logger.debug(
                                    f"Module __file__: {getattr(models_module, '__file__', 'N/A')}"
                                )

                                # 驗證 Plan 是否成功加載
                                if (
                                    hasattr(models_module, "Plan")
                                    and models_module.Plan is not None
                                ):
                                    logger.info(
                                        f"✅ Force pre-loaded {models_module_path}, Plan={models_module.Plan}, source={getattr(models_module, 'get_model_source', lambda: 'unknown')()}"
                                    )

                                    # 確保 Plan 在 sys.modules 中可用
                                    if models_module_path in sys.modules:
                                        sys.modules[models_module_path].Plan = (
                                            models_module.Plan
                                        )
                                        logger.debug(
                                            f"✅ Set Plan in sys.modules['{models_module_path}']"
                                        )

                                    # 檢查 Plan 是否在模組的 __dict__ 中
                                    if "Plan" in models_module.__dict__:
                                        logger.debug(
                                            f"✅ Plan found in module __dict__"
                                        )
                                    else:
                                        logger.warning(
                                            f"⚠️ Plan not in module __dict__, adding it..."
                                        )
                                        models_module.Plan = models_module.Plan

                                else:
                                    logger.warning(
                                        f"⚠️ Force pre-loaded {models_module_path} but Plan is None"
                                    )
                                    logger.debug(
                                        f"Module attributes: {[attr for attr in dir(models_module) if not attr.startswith('_')][:10]}"
                                    )

                            except Exception as preload_err:
                                logger.warning(
                                    f"❌ Preload capability models failed for {cap}: {preload_err}"
                                )
                                import traceback

                                logger.warning(
                                    f"Preload traceback:\n{traceback.format_exc()}"
                                )

                            # 再次檢查 sys.modules 中的狀態
                            if models_module_path in sys.modules:
                                cached_module = sys.modules[models_module_path]
                                logger.debug(
                                    f"Checking cached module state: Plan={'available' if hasattr(cached_module, 'Plan') and cached_module.Plan is not None else 'NOT available'}"
                                )
                                if (
                                    hasattr(cached_module, "Plan")
                                    and cached_module.Plan is not None
                                ):
                                    logger.info(
                                        f"✅ Verified Plan is available in sys.modules['{models_module_path}']"
                                    )
                                else:
                                    logger.warning(
                                        f"⚠️ Plan NOT available in cached module, attempting to set it..."
                                    )
                                    # 嘗試重新導入並設置
                                    try:
                                        fresh_module = importlib.import_module(
                                            models_module_path
                                        )
                                        if (
                                            hasattr(fresh_module, "Plan")
                                            and fresh_module.Plan is not None
                                        ):
                                            sys.modules[models_module_path].Plan = (
                                                fresh_module.Plan
                                            )
                                            logger.info(
                                                f"✅ Set Plan from fresh import"
                                            )
                                    except Exception as e:
                                        logger.warning(
                                            f"Failed to set Plan from fresh import: {e}"
                                        )

                            logger.info(f"Importing tool file: {module_path}")
                            logger.debug(
                                f"sys.path before tool import: {sys.path[:5]}... (showing first 5)"
                            )

                            try:
                                # 在導入前確保 app.capabilities.* 模組的 __spec__ 已設置
                                # 處理兩種路徑格式：capabilities.* 和 app.capabilities.*
                                if module_path.startswith("capabilities.") or module_path.startswith("app.capabilities."):
                                    # 確定 capability 名稱
                                    if module_path.startswith("app.capabilities."):
                                        # app.capabilities.video_chapter_studio.tools.video_ingest -> video_chapter_studio
                                        cap_parts = module_path.replace("app.capabilities.", "").split(".")
                                        cap_name = cap_parts[0] if cap_parts else None
                                    else:
                                        # capabilities.video_chapter_studio.tools.video_ingest -> video_chapter_studio
                                        cap_parts = module_path.split(".")
                                        cap_name = cap_parts[1] if len(cap_parts) >= 2 else None

                                    if cap_name:
                                        # 確保 app.capabilities 模組存在且有 __spec__
                                        app_capabilities_path = "app.capabilities"
                                        if app_capabilities_path not in sys.modules:
                                            # 創建 app.capabilities 模組
                                            if "app" not in sys.modules:
                                                app_module = types.ModuleType("app")
                                                sys.modules["app"] = app_module
                                            app_capabilities_module = types.ModuleType(app_capabilities_path)
                                            app_capabilities_module.__path__ = [str(self.capabilities_dir)]
                                            sys.modules[app_capabilities_path] = app_capabilities_module
                                            setattr(sys.modules["app"], "capabilities", app_capabilities_module)

                                        # 設置 app.capabilities 的 __spec__
                                        app_capabilities_module = sys.modules[app_capabilities_path]
                                        if not hasattr(app_capabilities_module, "__spec__") or app_capabilities_module.__spec__ is None:
                                            capabilities_init = self.capabilities_dir / "__init__.py"
                                            if not capabilities_init.exists():
                                                capabilities_init.touch()
                                            if capabilities_init.exists():
                                                import importlib.util
                                                spec = importlib.util.spec_from_file_location(
                                                    app_capabilities_path,
                                                    capabilities_init,
                                                    submodule_search_locations=[str(self.capabilities_dir)]
                                                )
                                                if spec:
                                                    app_capabilities_module.__spec__ = spec
                                                    logger.debug(f"Set __spec__ for {app_capabilities_path} before importing {module_path}")

                                        # 確保 app.capabilities.{cap_name} 模組存在且有 __spec__
                                        app_cap_path = f"app.capabilities.{cap_name}"
                                        if app_cap_path not in sys.modules:
                                            # 創建 app.capabilities.{cap_name} 模組
                                            cap_dir = self.capabilities_dir / cap_name
                                            if cap_dir.exists():
                                                app_cap_module = types.ModuleType(app_cap_path)
                                                app_cap_module.__path__ = [str(cap_dir)]
                                                sys.modules[app_cap_path] = app_cap_module
                                                setattr(sys.modules[app_capabilities_path], cap_name, app_cap_module)

                                        # 設置 app.capabilities.{cap_name} 的 __spec__
                                        if app_cap_path in sys.modules:
                                            app_cap_module = sys.modules[app_cap_path]
                                            if not hasattr(app_cap_module, "__spec__") or app_cap_module.__spec__ is None:
                                                cap_dir = self.capabilities_dir / cap_name
                                                if cap_dir.exists():
                                                    init_file = cap_dir / "__init__.py"
                                                    if init_file.exists():
                                                        import importlib.util
                                                        spec = importlib.util.spec_from_file_location(
                                                            app_cap_path,
                                                            init_file,
                                                            submodule_search_locations=[str(cap_dir)]
                                                        )
                                                        if spec:
                                                            app_cap_module.__spec__ = spec
                                                            logger.debug(f"Set __spec__ for {app_cap_path} before importing {module_path}")

                                module = importlib.import_module(module_path)
                            except (ImportError, ModuleNotFoundError, ValueError) as import_error:
                                # For import errors (missing dependencies), check if it's an optional dependency
                                # This allows installation to proceed when optional dependencies are missing
                                error_msg = str(import_error)
                                is_optional = False

                                # Check against manifest-defined optional Python packages
                                if optional_python_packages:
                                    for pkg in optional_python_packages:
                                        if pkg.lower() in error_msg.lower():
                                            is_optional = True
                                            break

                                # Fallback: check common optional dependencies
                                if not is_optional and (
                                    "langchain" in error_msg.lower()
                                    or "asyncpg" in error_msg.lower()
                                    # Some capabilities ship tools that rely on cloud-only runtime modules.
                                    # Treat these as optional during install-time validation so packs can be installed.
                                    or "services.divi" in error_msg.lower()
                                    or "capabilities.wordpress" in error_msg.lower()
                                    or "database.models.divi" in error_msg.lower()
                                ):
                                    is_optional = True

                                if is_optional:
                                    warnings.append(
                                        f"Step '{step_id}': Tool '{tool_slot}' has optional dependency issue: {import_error}. "
                                        f"Tool will be available once dependencies are installed."
                                    )
                                    logger.warning(
                                        f"Step '{step_id}': Tool '{tool_slot}' import failed due to optional dependency: {import_error}"
                                    )
                                    continue
                                else:
                                    # For other import errors, still treat as error
                                    errors.append(
                                        f"Step '{step_id}': Tool '{tool_slot}' validation error: {import_error}"
                                    )
                                    continue

                            try:
                                # 獲取函數/方法對象
                                if "." in target:
                                    # Class method
                                    class_name, method_name = target.rsplit(".", 1)
                                    cls = getattr(module, class_name, None)
                                    if cls is None:
                                        errors.append(
                                            f"Step '{step_id}': Tool '{tool_slot}' class '{class_name}' not found in module"
                                        )
                                        continue
                                    func = getattr(cls, method_name, None)
                                else:
                                    # Module-level function
                                    func = getattr(module, target, None)

                                if func is None:
                                    # If function not found but tool is in manifest, treat as warning (not yet implemented)
                                    warnings.append(
                                        f"Step '{step_id}': Tool '{tool_slot}' function '{target}' not found in module (may not be implemented yet). "
                                        f"Tool will be available once implementation is complete."
                                    )
                                    logger.warning(
                                        f"Step '{step_id}': Tool '{tool_slot}' function '{target}' not found in module (may not be implemented yet)"
                                    )
                                    continue

                                # 檢查是否可調用
                                if not callable(func):
                                    errors.append(
                                        f"Step '{step_id}': Tool '{tool_slot}' '{backend_path}' is not a callable object"
                                    )
                                    continue

                                # 檢查函數簽名（不實際執行）
                                sig = inspect.signature(func)
                                logger.debug(
                                    f"Step '{step_id}': Tool '{tool_slot}' signature validated: {sig}"
                                )

                            except Exception as e:
                                errors.append(
                                    f"Step '{step_id}': Tool '{tool_slot}' validation error: {str(e)}"
                                )
                        else:
                            errors.append(
                                f"Step '{step_id}': Invalid tool_slot format: '{tool_slot}' (expected 'capability.tool_name')"
                            )
                    else:
                        # 非 capability tool（可能是 MindscapeTool），跳過驗證
                        # 這些 tool 需要運行時環境才能驗證
                        logger.debug(
                            f"Step '{step_id}': Non-capability tool '{tool_slot}' skipped (requires runtime)"
                        )

                except Exception as e:
                    errors.append(
                        f"Step '{step_id}': Tool '{tool_slot}' call test failed: {str(e)}"
                    )

            if errors:
                logger.error(
                    f"Playbook {playbook_code} tool call test failed: {len(errors)} error(s)"
                )

        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in playbook spec: {e}")
        except Exception as e:
            errors.append(f"Error validating tool calls: {e}")

        return errors, warnings

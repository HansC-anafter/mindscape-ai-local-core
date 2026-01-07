"""
Bootstrap Strategies

Uses strategy pattern to handle different types of bootstrap operations,
avoiding hardcoded business logic. All special handling is declared through manifest configuration.
"""

import logging
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class BootstrapStrategy(ABC):
    """Bootstrap strategy base class"""

    @abstractmethod
    def execute(
        self,
        local_core_root: Path,
        cap_dir: Path,
        capability_code: str,
        config: Dict,
        result
    ) -> bool:
        """
        Execute bootstrap operation

        Args:
            local_core_root: Local-core project root directory
            cap_dir: Capability package directory
            capability_code: Capability code
            config: Strategy configuration (from manifest bootstrap config)
            result: InstallResult object

        Returns:
            True if execution succeeds
        """
        pass

    @abstractmethod
    def get_type(self) -> str:
        """Return strategy type identifier"""
        pass


class PythonScriptStrategy(BootstrapStrategy):
    """Strategy for executing Python scripts"""

    def get_type(self) -> str:
        return "python_script"

    def execute(
        self,
        local_core_root: Path,
        cap_dir: Path,
        capability_code: str,
        config: Dict,
        result
    ) -> bool:
        script_path = config.get('path')
        if not script_path:
            logger.warning(f"Python script bootstrap: missing 'path' in config")
            result.add_warning("Bootstrap script: missing 'path'")
            return False

        script_full_path = cap_dir / script_path
        if not script_full_path.exists():
            logger.warning(f"Bootstrap script not found: {script_full_path}")
            result.add_warning(f"Bootstrap script not found: {script_path}")
            return False

        try:
            logger.info(f"Running bootstrap script: {script_full_path}")
            process_result = subprocess.run(
                [sys.executable, str(script_full_path)],
                cwd=str(local_core_root),
                capture_output=True,
                text=True,
                timeout=config.get('timeout', 60)
            )

            if process_result.returncode == 0:
                logger.info(f"Bootstrap script completed: {script_full_path}")
                result.bootstrap.append(str(script_full_path.name))
                return True
            else:
                error_msg = process_result.stderr or process_result.stdout
                logger.warning(f"Bootstrap script failed: {error_msg}")
                result.add_warning(f"Bootstrap script failed: {error_msg}")
                return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Bootstrap script timed out: {script_full_path}")
            result.add_warning(f"Bootstrap script timed out: {script_path}")
            return False
        except Exception as e:
            logger.warning(f"Bootstrap script error: {e}")
            result.add_warning(f"Bootstrap script error: {e}")
            return False


class ContentVaultInitStrategy(BootstrapStrategy):
    """Strategy for initializing Content Vault"""

    def get_type(self) -> str:
        return "content_vault_init"

    def execute(
        self,
        local_core_root: Path,
        cap_dir: Path,
        capability_code: str,
        config: Dict,
        result
    ) -> bool:
        vault_path = config.get('vault_path')

        try:
            script_path = local_core_root / "backend" / "scripts" / "init_content_vault.py"
            if not script_path.exists():
                logger.warning(f"Content Vault init script not found: {script_path}")
                result.add_warning("Content Vault init script not found")
                return False

            cmd = [sys.executable, str(script_path)]
            if vault_path:
                cmd.extend(["--vault-path", vault_path])

            logger.info("Running Content Vault initialization...")
            process_result = subprocess.run(
                cmd,
                cwd=str(local_core_root),
                capture_output=True,
                text=True,
                timeout=config.get('timeout', 30)
            )

            if process_result.returncode == 0:
                logger.info("Content Vault initialized successfully")
                result.bootstrap.append("content_vault_initialized")
                return True
            else:
                logger.warning(f"Content Vault initialization failed: {process_result.stderr}")
                result.add_warning(f"Content Vault initialization failed: {process_result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.warning("Content Vault initialization timed out")
            result.add_warning("Content Vault initialization timed out")
            return False
        except Exception as e:
            logger.warning(f"Failed to run Content Vault initialization: {e}")
            result.add_warning(f"Content Vault initialization error: {e}")
            return False


class SiteHubRuntimeInitStrategy(BootstrapStrategy):
    """Strategy for initializing Site-Hub Runtime (conditional execution)"""

    def get_type(self) -> str:
        return "site_hub_runtime_init"

    def execute(
        self,
        local_core_root: Path,
        cap_dir: Path,
        capability_code: str,
        config: Dict,
        result
    ) -> bool:
        """
        Auto-register Site-Hub runtime if environment variable is set.
        Skip silently if environment variable is not set.
        """
        site_hub_url = os.getenv("SITE_HUB_API_BASE") or os.getenv("SITE_HUB_URL")
        if not site_hub_url:
            logger.debug("SITE_HUB_API_BASE not set, skipping Site-Hub runtime auto-registration")
            if config.get('warn_if_missing', False):
                result.add_warning(
                    "Site-Hub runtime not auto-registered. "
                    "Set SITE_HUB_API_BASE environment variable or use 'site_hub_setup' playbook to register."
                )
            return True

        try:
            import httpx
            import asyncio

            async def check_runtime():
                try:
                    local_core_api = os.getenv("LOCAL_CORE_API_BASE", "http://localhost:8200")
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f"{local_core_api}/api/v1/runtime-environments")
                        if response.status_code == 200:
                            data = response.json()
                            runtimes = data.get("runtimes", []) if isinstance(data, dict) else data
                            for rt in runtimes:
                                if rt.get("id") == "site-hub" or (
                                    isinstance(rt.get("metadata", {}).get("signature", {}), dict) and
                                    rt.get("metadata", {}).get("signature", {}).get("base_url") == site_hub_url.rstrip("/")
                                ):
                                    logger.info("Site-Hub runtime already registered")
                                    result.bootstrap.append("site_hub_runtime_already_registered")
                                    return True
                    return False
                except Exception as e:
                    logger.debug(f"Site-Hub runtime check failed: {e}")
                    return False

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            already_registered = loop.run_until_complete(check_runtime())
            if already_registered:
                return True

            logger.info("Site-Hub runtime auto-registration skipped (requires user context)")
            if config.get('warn_if_missing', True):
                result.add_warning(
                    "Site-Hub runtime auto-registration requires user context. "
                    "Please use 'site_hub_setup' playbook or call 'site_hub_register_runtime' tool to register."
                )
            return True

        except ImportError:
            logger.debug("httpx not available for Site-Hub runtime check")
            if config.get('warn_if_missing', False):
                result.add_warning(
                    "Site-Hub runtime auto-registration skipped (tools not available). "
                    "Please use 'site_hub_setup' playbook to register."
                )
            return True
        except Exception as e:
            logger.warning(f"Site-Hub runtime auto-registration check failed: {e}")
            if config.get('warn_if_missing', False):
                result.add_warning(
                    f"Site-Hub runtime auto-registration skipped: {str(e)}. "
                    "Please use 'site_hub_setup' playbook to register."
                )
            return True


class ConditionalBootstrapStrategy(BootstrapStrategy):
    """
    Conditional execution strategy: executes another strategy based on conditions
    (e.g., capability code matching). Used to replace hardcoded capability code lists.
    """

    def get_type(self) -> str:
        return "conditional"

    def execute(
        self,
        local_core_root: Path,
        cap_dir: Path,
        capability_code: str,
        config: Dict,
        result
    ) -> bool:
        """
        Execute sub-strategy based on condition

        Config format:
        {
            "condition": {
                "type": "capability_code_in",  # or "capability_code_match", "env_var_set", etc.
                "value": ["ig_post", "ig_post_generation", ...]  # or regex pattern, env var name
            },
            "strategy": {
                "type": "content_vault_init",  # or other strategy type
                ...  # strategy-specific config
            }
        }
        """
        condition = config.get('condition', {})
        condition_type = condition.get('type')
        condition_value = condition.get('value')

        should_execute = False
        if condition_type == 'capability_code_in':
            if isinstance(condition_value, list):
                should_execute = capability_code in condition_value
        elif condition_type == 'capability_code_match':
            import re
            if isinstance(condition_value, str):
                should_execute = bool(re.match(condition_value, capability_code))
        elif condition_type == 'env_var_set':
            if isinstance(condition_value, str):
                should_execute = bool(os.getenv(condition_value))
        elif condition_type == 'always':
            should_execute = True
        else:
            logger.warning(f"Unknown condition type: {condition_type}")
            return False

        if not should_execute:
            logger.debug(f"Condition not met for bootstrap: {condition_type}={condition_value}")
            return True

        strategy_config = config.get('strategy', {})
        strategy_type = strategy_config.get('type')
        if not strategy_type:
            logger.warning("Conditional bootstrap: missing strategy type")
            return False
        from .bootstrap_registry import BootstrapRegistry
        registry = BootstrapRegistry()
        strategy = registry.get_strategy(strategy_type)
        if not strategy:
            logger.warning(f"Unknown bootstrap strategy type: {strategy_type}")
            result.add_warning(f"Unknown bootstrap strategy type: {strategy_type}")
            return False

        return strategy.execute(
            local_core_root,
            cap_dir,
            capability_code,
            strategy_config,
            result
        )



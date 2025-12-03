"""
System Health Checker Service

Checks system health status including:
- LLM API key configuration
- Vector DB connection
- Tool connections (WordPress, Obsidian, Notion, etc.)
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from backend.app.services.config_store import ConfigStore
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.backend_manager import BackendManager

logger = logging.getLogger(__name__)


class HealthIssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class HealthIssue:
    def __init__(
        self,
        issue_type: str,
        severity: HealthIssueSeverity,
        message: str,
        action_url: Optional[str] = None,
        tool_type: Optional[str] = None
    ):
        self.type = issue_type
        self.severity = severity
        self.message = message
        self.action_url = action_url
        self.tool_type = tool_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity.value,
            "message": self.message,
            "action_url": self.action_url,
            "tool_type": self.tool_type
        }


class SystemHealthChecker:
    """System health checker service"""

    def __init__(
        self,
        config_store: Optional[ConfigStore] = None,
        tool_registry: Optional[ToolRegistryService] = None,
        backend_manager: Optional[BackendManager] = None
    ):
        import os
        self.config_store = config_store or ConfigStore()
        data_dir = os.getenv("DATA_DIR", "./data")
        self.tool_registry = tool_registry or ToolRegistryService(data_dir=data_dir)
        self.backend_manager = backend_manager or BackendManager(config_store=self.config_store)

    async def check_workspace_health(
        self,
        profile_id: str,
        workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check system health for a workspace

        Args:
            profile_id: User profile ID
            workspace_id: Optional workspace ID

        Returns:
            Health status dictionary
        """
        issues: List[HealthIssue] = []
        tools_status: Dict[str, Dict[str, Any]] = {}

        # Check backend service
        backend_status = await self._check_backend_service(issues)

        # Check OCR service
        ocr_status = await self._check_ocr_service(issues)

        # Check LLM configuration
        llm_status = await self._check_llm_configuration(profile_id, issues)

        # Check Vector DB connection
        vector_db_status = await self._check_vector_db(issues)

        # Check tool connections
        tools_status = await self._check_tool_connections(profile_id, issues)

        return {
            "backend": backend_status,
            "ocr_service": ocr_status,
            "llm_configured": llm_status["configured"],
            "llm_provider": llm_status.get("provider"),
            "llm_available": llm_status.get("available", False),
            "vector_db_connected": vector_db_status["connected"],
            "tools": tools_status,
            "issues": [issue.to_dict() for issue in issues],
            "overall_status": "healthy" if not any(i.severity == HealthIssueSeverity.ERROR for i in issues) else "unhealthy"
        }

    async def _check_llm_configuration(
        self,
        profile_id: str,
        issues: List[HealthIssue]
    ) -> Dict[str, Any]:
        """Check LLM API key configuration by actually testing the connection"""
        try:
            config = self.config_store.get_or_create_config(profile_id)
            available_backends = self.backend_manager.get_available_backends()

            current_mode = config.agent_backend.mode
            current_backend = available_backends.get(current_mode, {})

            provider = current_mode

            # Actually test the connection instead of just checking if backend is available
            # Test LLM connection by making an actual API call
            configured = False
            available = False

            try:
                import os
                from backend.app.services.system_settings_store import SystemSettingsStore

                settings_store = SystemSettingsStore()
                chat_setting = settings_store.get_setting("chat_model")

                if chat_setting:
                    model_name = str(chat_setting.value)
                    provider = chat_setting.metadata.get("provider", "openai") if hasattr(chat_setting, 'metadata') else "openai"

                    # Get API key
                    if provider == "openai":
                        api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
                    elif provider == "anthropic":
                        api_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
                    else:
                        api_key = None

                    if api_key:
                        # Test connection with a simple API call
                        try:
                            if provider == "openai":
                                import openai
                                client = openai.OpenAI(api_key=api_key)
                                create_params = {
                                    "model": model_name,
                                    "messages": [{"role": "user", "content": "Hi"}]
                                }
                                if not (model_name.startswith("gpt-5") or "gpt-5" in model_name):
                                    create_params["max_tokens"] = 10
                                response = client.chat.completions.create(**create_params)
                                configured = bool(response.choices and len(response.choices) > 0)
                                available = configured
                            elif provider == "anthropic":
                                import anthropic
                                client = anthropic.Anthropic(api_key=api_key)
                                response = client.messages.create(
                                    model=model_name,
                                    max_tokens=10,
                                    messages=[{"role": "user", "content": "Hello"}]
                                )
                                configured = bool(response.content)
                                available = configured
                        except Exception as api_error:
                            logger.warning(f"LLM connection test failed: {api_error}")
                            configured = False
                            available = False

                            if current_mode == "local":
                                error_msg = str(api_error)
                                issues.append(HealthIssue(
                                    issue_type="api_key_invalid",
                                    severity=HealthIssueSeverity.ERROR,
                                    message=f"LLM API key 可能无效或已过期: {error_msg}",
                                    action_url="/settings?tab=llm"
                                ))
                    else:
                        if current_mode == "local":
                            issues.append(HealthIssue(
                                issue_type="api_key_missing",
                                severity=HealthIssueSeverity.ERROR,
                                message="LLM API key 尚未设定（OpenAI 或 Anthropic）",
                                action_url="/settings?tab=llm"
                            ))
                else:
                    # No chat model configured, check if API keys exist
                    if current_mode == "local":
                        if config.agent_backend.openai_api_key or config.agent_backend.anthropic_api_key:
                            # Has keys but no model configured
                            configured = current_backend.get("available", False)
                            available = configured
                        else:
                            issues.append(HealthIssue(
                                issue_type="api_key_missing",
                                severity=HealthIssueSeverity.ERROR,
                                message="LLM API key 尚未设定（OpenAI 或 Anthropic）",
                                action_url="/settings?tab=llm"
                            ))
                            configured = False
                            available = False
                    elif current_mode == "remote_crs":
                        if not config.agent_backend.remote_crs_url or not config.agent_backend.remote_crs_token:
                            issues.append(HealthIssue(
                                issue_type="remote_crs_not_configured",
                                severity=HealthIssueSeverity.ERROR,
                                message="Remote CRS 尚未配置",
                                action_url="/settings?tab=backend"
                            ))
                            configured = False
                            available = False
                        else:
                            configured = current_backend.get("available", False)
                            available = configured
            except Exception as test_error:
                logger.warning(f"LLM connection test error: {test_error}")
                # Fallback to old method
                configured = current_backend.get("available", False)
                available = configured

                if not configured and current_mode == "local":
                    if not config.agent_backend.openai_api_key and not config.agent_backend.anthropic_api_key:
                        issues.append(HealthIssue(
                            issue_type="api_key_missing",
                            severity=HealthIssueSeverity.ERROR,
                            message="LLM API key 尚未设定（OpenAI 或 Anthropic）",
                            action_url="/settings?tab=llm"
                        ))

            return {
                "configured": configured,
                "provider": provider,
                "available": available
            }
        except Exception as e:
            logger.error(f"Failed to check LLM configuration: {e}", exc_info=True)
            issues.append(HealthIssue(
                issue_type="llm_check_failed",
                severity=HealthIssueSeverity.ERROR,
                message=f"检查 LLM 配置时发生错误: {str(e)}",
                action_url="/settings"
            ))
            return {
                "configured": False,
                "provider": None,
                "available": False
            }

    async def _check_vector_db(self, issues: List[HealthIssue]) -> Dict[str, Any]:
        """Check Vector DB connection using actual connection test"""
        try:
            # Use comprehensive connection test including pgvector extension check
            try:
                from backend.app.routes.vector_db import get_config, get_local_postgres_config
                import psycopg2
                from psycopg2.extras import RealDictCursor

                # Get current config
                config = await get_config()

                # Determine connection parameters
                if config.mode == "local":
                    local_config = get_local_postgres_config()
                    conn_params = {
                        "host": local_config["host"],
                        "port": local_config["port"],
                        "database": local_config["database"],
                        "user": local_config["user"],
                        "password": local_config["password"],
                    }
                else:
                    password = config.password
                    if not password:
                        from backend.app.routes.vector_db import get_connection
                        with get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute('SELECT password FROM vector_db_config ORDER BY id DESC LIMIT 1')
                            row = cursor.fetchone()
                            password = row["password"] if row else None

                    if not config.host or not config.username or not password:
                        return {"connected": False}

                    conn_params = {
                        "host": config.host,
                        "port": config.port,
                        "database": config.database,
                        "user": config.username,
                        "password": password,
                    }

                    if config.ssl_mode == "require":
                        conn_params["sslmode"] = "require"
                    elif config.ssl_mode == "prefer":
                        conn_params["sslmode"] = "prefer"

                # Test connection and check pgvector
                pg_conn = psycopg2.connect(**conn_params)
                cursor = pg_conn.cursor(cursor_factory=RealDictCursor)

                # Check pgvector extension
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM pg_extension WHERE extname = 'vector'
                    ) as installed
                """)
                pgvector_check = cursor.fetchone()
                pgvector_installed = pgvector_check and pgvector_check["installed"]

                # Get pgvector version if installed
                pgvector_version = None
                if pgvector_installed:
                    cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                    version_row = cursor.fetchone()
                    pgvector_version = version_row["extversion"] if version_row else None

                cursor.close()
                pg_conn.close()

                connected = pgvector_installed

                if not connected:
                    if not pgvector_installed:
                        issues.append(HealthIssue(
                            issue_type="pgvector_not_installed",
                            severity=HealthIssueSeverity.WARNING,
                            message="pgvector 扩展未安装，语义搜索功能不可用",
                            action_url="/settings?tab=database"
                        ))

                return {
                    "connected": connected,
                    "pgvector_installed": pgvector_installed,
                    "pgvector_version": pgvector_version
                }
            except ImportError:
                # Fallback to old method if test function not available
                logger.warning("Vector DB comprehensive test not available, using fallback check")
                from backend.app.services.vector_search import VectorSearchService
                vector_service = VectorSearchService()
                connected = await vector_service.check_connection()

                if not connected:
                    issues.append(HealthIssue(
                        issue_type="vector_db_not_connected",
                        severity=HealthIssueSeverity.WARNING,
                        message="Vector DB 未连接，语义搜索功能可能不可用",
                        action_url="/settings?tab=database"
                    ))

                return {
                    "connected": connected
                }
            except Exception as conn_error:
                logger.warning(f"Vector DB comprehensive test failed: {conn_error}")
                # Fallback to simple check
                from backend.app.services.vector_search import VectorSearchService
                vector_service = VectorSearchService()
                connected = await vector_service.check_connection()

                if not connected:
                    issues.append(HealthIssue(
                        issue_type="vector_db_not_connected",
                        severity=HealthIssueSeverity.WARNING,
                        message="Vector DB 连接检查失败，语义搜索功能可能不可用",
                        action_url="/settings?tab=database"
                    ))

                return {
                    "connected": connected
                }
        except ImportError:
            logger.warning("Vector DB check not available")
            return {"connected": False}
        except Exception as e:
            logger.error(f"Failed to check Vector DB: {e}", exc_info=True)
            issues.append(HealthIssue(
                issue_type="vector_db_check_failed",
                severity=HealthIssueSeverity.WARNING,
                message=f"检查 Vector DB 连接时发生错误: {str(e)}",
                action_url="/settings?tab=database"
            ))
            return {"connected": False}

    async def _check_backend_service(self, issues: List[HealthIssue]) -> Dict[str, Any]:
        """Check backend API service health"""
        # If we're already in the backend service checking itself, just return healthy
        # to avoid infinite loop or unnecessary HTTP calls
        return {
            "status": "healthy",
            "available": True,
            "url": "http://localhost:8000"
        }

    async def _check_ocr_service(self, issues: List[HealthIssue]) -> Dict[str, Any]:
        """Check OCR service health"""
        try:
            from backend.app.capabilities.core_files.services.ocr_client import get_ocr_client

            ocr_client = get_ocr_client()
            health_data = await ocr_client.check_health()

            if health_data.get("status") == "ok":
                return {
                    "status": "healthy",
                    "available": True,
                    "gpu_available": health_data.get("gpu_available", False),
                    "gpu_enabled": health_data.get("gpu_enabled", False),
                    "service": health_data.get("service", "ocr-service")
                }
            else:
                issues.append(HealthIssue(
                    issue_type="ocr_service_unhealthy",
                    severity=HealthIssueSeverity.WARNING,
                    message=f"OCR service unhealthy: {health_data.get('error', 'unknown')}",
                    action_url="/settings?tab=service_status"
                ))
                return {
                    "status": "unhealthy",
                    "available": False,
                    "error": health_data.get("error", "unknown")
                }
        except Exception as e:
            logger.warning(f"OCR service health check failed: {e}")
            issues.append(HealthIssue(
                issue_type="ocr_service_unavailable",
                severity=HealthIssueSeverity.WARNING,
                message=f"OCR service unavailable: {str(e)}. Local OCR features may not work.",
                action_url="/settings?tab=service_status"
            ))
            return {
                "status": "unavailable",
                "available": False,
                "error": str(e)
            }

    async def _check_tool_connections(
        self,
        profile_id: str,
        issues: List[HealthIssue]
    ) -> Dict[str, Dict[str, Any]]:
        """Check tool connections status"""
        tools_status: Dict[str, Dict[str, Any]] = {}

        tool_types_to_check = ["wordpress", "obsidian", "notion", "google_drive"]

        try:
            for tool_type in tool_types_to_check:
                connections = self.tool_registry.get_connections_by_tool_type(
                    profile_id, tool_type
                )
                active_connections = [c for c in connections if c.is_active]

                if active_connections:
                    tools_status[tool_type] = {
                        "connected": True,
                        "status": "ok",
                        "connection_count": len(active_connections)
                    }
                else:
                    tools_status[tool_type] = {
                        "connected": False,
                        "status": "not_configured",
                        "connection_count": 0
                    }

                    if tool_type in ["wordpress", "obsidian", "notion"]:
                        issues.append(HealthIssue(
                            issue_type=f"{tool_type}_not_configured",
                            severity=HealthIssueSeverity.INFO,
                            message=f"{tool_type.capitalize()} 尚未連接",
                            action_url=f"/settings?tab=tools&tool={tool_type}",
                            tool_type=tool_type
                        ))

        except Exception as e:
            logger.error(f"Failed to check tool connections: {e}", exc_info=True)
            for tool_type in tool_types_to_check:
                tools_status[tool_type] = {
                    "connected": False,
                    "status": "check_failed",
                    "error": str(e)
                }

        return tools_status

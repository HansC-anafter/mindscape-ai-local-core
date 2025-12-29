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

                    # Get API key or Vertex AI configuration
                    if provider == "openai":
                        api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
                        vertex_ai_configured = False
                    elif provider == "anthropic":
                        api_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
                        vertex_ai_configured = False
                    elif provider == "vertex-ai":
                        # Check Vertex AI configuration
                        vertex_ai_service_account = settings_store.get_setting("vertex_ai_service_account_json")
                        vertex_ai_project_id = settings_store.get_setting("vertex_ai_project_id")
                        vertex_ai_location = settings_store.get_setting("vertex_ai_location")
                        vertex_ai_configured = bool(
                            vertex_ai_service_account and
                            vertex_ai_service_account.value and
                            vertex_ai_project_id and
                            vertex_ai_project_id.value
                        )
                        api_key = None  # Vertex AI doesn't use API key
                    else:
                        api_key = None
                        vertex_ai_configured = False

                    if api_key or vertex_ai_configured:
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
                            elif provider == "vertex-ai":
                                # For Vertex AI, if configuration exists, consider it configured
                                # Actual connection test would require GCP credentials setup
                                configured = vertex_ai_configured
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
                                    message=f"LLM API key may be invalid or expired: {error_msg}",
                                    action_url="/settings?tab=llm"
                                ))
                    else:
                        if current_mode == "local":
                            if provider == "vertex-ai":
                                issues.append(HealthIssue(
                                    issue_type="vertex_ai_not_configured",
                                    severity=HealthIssueSeverity.ERROR,
                                    message="Vertex AI is not configured (service account JSON and project ID required)",
                                    action_url="/settings?tab=llm"
                                ))
                            else:
                                # Missing API key is a WARNING, not ERROR, to allow system startup
                                # Some features may be unavailable, but core functionality should work
                                issues.append(HealthIssue(
                                    issue_type="api_key_missing",
                                    severity=HealthIssueSeverity.WARNING,
                                    message="LLM API key not configured (OpenAI or Anthropic). Some AI features may be unavailable.",
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
                            # Missing API key is a WARNING, not ERROR, to allow system startup
                            # Some features may be unavailable, but core functionality should work
                            issues.append(HealthIssue(
                                issue_type="api_key_missing",
                                severity=HealthIssueSeverity.WARNING,
                                message="LLM API key not configured (OpenAI or Anthropic). Some AI features may be unavailable.",
                                action_url="/settings?tab=llm"
                            ))
                            configured = False
                            available = False
                    elif current_mode == "remote_crs":
                        if not config.agent_backend.remote_crs_url or not config.agent_backend.remote_crs_token:
                            issues.append(HealthIssue(
                                issue_type="remote_crs_not_configured",
                                severity=HealthIssueSeverity.ERROR,
                                message="Remote CRS is not configured",
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
                        # Missing API key is a WARNING, not ERROR, to allow system startup
                        # Some features may be unavailable, but core functionality should work
                        issues.append(HealthIssue(
                            issue_type="api_key_missing",
                            severity=HealthIssueSeverity.WARNING,
                            message="LLM API key not configured (OpenAI or Anthropic). Some AI features may be unavailable.",
                            action_url="/settings?tab=llm"
                        ))

            # Normalize provider name for consistent display
            provider_display = provider
            if provider == "vertex-ai" or provider == "vertex_ai":
                provider_display = "vertex-ai"
            elif provider == "anthropic":
                provider_display = "anthropic"
            elif provider == "openai":
                provider_display = "openai"

            return {
                "configured": configured,
                "provider": provider_display,
                "available": available
            }
        except Exception as e:
            logger.error(f"Failed to check LLM configuration: {e}", exc_info=True)
            issues.append(HealthIssue(
                issue_type="llm_check_failed",
                severity=HealthIssueSeverity.ERROR,
                message=f"Error checking LLM configuration: {str(e)}",
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
                            message="pgvector extension not installed, semantic search unavailable",
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
                        message="Vector DB not connected, semantic search may be unavailable",
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
                        message="Vector DB connection check failed, semantic search may be unavailable",
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
                message=f"Error checking Vector DB connection: {str(e)}",
                action_url="/settings?tab=database"
            ))
            return {"connected": False}

    async def _check_backend_service(self, issues: List[HealthIssue]) -> Dict[str, Any]:
        """Check backend API service health"""
        # If we're already in the backend service checking itself, just return healthy
        # to avoid infinite loop or unnecessary HTTP calls
        # 从端口配置服务获取后端 URL
        try:
            from .port_config_service import port_config_service
            import os
            current_cluster = os.getenv('CLUSTER_NAME')
            current_env = os.getenv('ENVIRONMENT')
            current_site = os.getenv('SITE_NAME')
            url = port_config_service.get_service_url(
                'backend_api',
                cluster=current_cluster,
                environment=current_env,
                site=current_site
            )
        except Exception:
            url = "http://localhost:8200"

        return {
            "status": "healthy",
            "available": True,
            "url": url
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
                            message=f"{tool_type.capitalize()} is not connected",
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

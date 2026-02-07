"""
端口配置服务
提供统一的端口配置管理接口
"""

import os
import json
import logging
from typing import Optional, Dict, Tuple, List
from ..models.port_config import PortConfig, ServiceURLConfig, HostConfig
from .system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)

# 创建全局 settings_store 实例
settings_store = SystemSettingsStore()


class PortConfigService:
    """端口配置服务"""

    # 默认端口配置（新端口规划）
    DEFAULT_PORTS = {
        "backend_api": 8200,
        "frontend": 8300,
        "ocr_service": 8400,
        "postgres": 5440,
        "cloud_api": 8500,
        "site_hub_api": 8102,
        "media_proxy": 8202,
    }

    # 环境变量映射（向后兼容）
    ENV_VAR_MAPPING = {
        "backend_api": "BACKEND_PORT",
        "frontend": "FRONTEND_PORT",
        "ocr_service": "OCR_PORT",
        "postgres": "POSTGRES_PORT",
        "cloud_api": "CLOUD_API_PORT",
        "site_hub_api": "SITE_HUB_API_PORT",
        "media_proxy": "MEDIA_PROXY_PORT",
    }

    def __init__(self):
        self._config_cache: Optional[PortConfig] = None
        self._cache_key: Optional[str] = None

    def get_port_config(
        self,
        cluster: Optional[str] = None,
        environment: Optional[str] = None,
        site: Optional[str] = None,
        force_reload: bool = False,
    ) -> PortConfig:
        """
        获取端口配置（支持集群/环境/站点作用域）

        优先级（从最具体到最通用）:
        1. 系统设置 (system.ports.{cluster}.{env}.{site}.*) - 集群+环境+站点
        2. 系统设置 (system.ports.{cluster}.{env}.*) - 集群+环境
        3. 系统设置 (system.ports.{cluster}.{site}.*) - 集群+站点（跳过环境）
        4. 系统设置 (system.ports.{cluster}.*) - 仅集群
        5. 系统设置 (system.ports.{env}.{site}.*) - 环境+站点（无集群）
        6. 系统设置 (system.ports.{env}.*) - 仅环境（无集群）
        7. 系统设置 (system.ports.{site}.*) - 仅站点（无集群和环境）
        8. 系统设置 (system.ports.*) - 全局默认
        9. 环境变量 (BACKEND_PORT, etc.)
        10. 默认值 (DEFAULT_PORTS)

        Args:
            cluster: 集群标识
            environment: 环境标识
            site: 站点标识
            force_reload: 强制重新加载
        """
        config_dict = {}

        # 使用实际查询值作为缓存键（确保缓存一致性）
        cache_key = f"{cluster}:{environment}:{site}"
        if self._config_cache and not force_reload and cache_key == self._cache_key:
            return self._config_cache

        for key, default_port in self.DEFAULT_PORTS.items():
            port_value = None

            # 1. 尝试从作用域系统设置读取（从最具体到最通用）
            setting_keys = []

            # 最具体：cluster + environment + site
            if cluster and environment and site:
                setting_keys.append(
                    f"system.ports.{cluster}.{environment}.{site}.{key}"
                )

            # cluster + environment
            if cluster and environment:
                setting_keys.append(f"system.ports.{cluster}.{environment}.{key}")

            # cluster + site（跳过 environment）
            if cluster and site:
                setting_keys.append(f"system.ports.{cluster}.{site}.{key}")

            # 仅 cluster
            if cluster:
                setting_keys.append(f"system.ports.{cluster}.{key}")

            # environment + site（无 cluster）
            if environment and site and not cluster:
                setting_keys.append(f"system.ports.{environment}.{site}.{key}")

            # 仅 environment（无 cluster）
            if environment and not cluster:
                setting_keys.append(f"system.ports.{environment}.{key}")

            # 仅 site（无 cluster 和 environment）
            if site and not cluster and not environment:
                setting_keys.append(f"system.ports.{site}.{key}")

            # 全局默认
            setting_keys.append(f"system.ports.{key}")

            for setting_key in setting_keys:
                setting = settings_store.get_setting(setting_key)
                if setting and setting.value is not None:
                    try:
                        port_value = int(setting.value)
                        logger.debug(
                            f"从系统设置读取端口配置: {setting_key} = {port_value}"
                        )
                        break
                    except (ValueError, TypeError):
                        logger.warning(
                            f"系统设置中的端口值无效: {setting_key} = {setting.value}"
                        )

            # 2. 如果系统设置未找到，尝试从环境变量读取
            if port_value is None:
                env_var = self.ENV_VAR_MAPPING.get(key)
                if env_var:
                    env_value = os.getenv(env_var)
                    if env_value:
                        try:
                            port_value = int(env_value)
                            logger.debug(
                                f"从环境变量读取端口配置: {env_var} = {port_value}"
                            )
                        except (ValueError, TypeError):
                            logger.warning(
                                f"环境变量中的端口值无效: {env_var} = {env_value}"
                            )

            # 3. 使用默认值
            config_dict[key] = port_value if port_value is not None else default_port
            if port_value is None:
                logger.debug(f"使用默认端口配置: {key} = {default_port}")

        # 添加作用域信息（保留原始传入值，不添加默认值）
        config_dict["cluster"] = cluster
        config_dict["environment"] = environment
        config_dict["site"] = site

        self._config_cache = PortConfig(**config_dict)
        self._cache_key = cache_key
        return self._config_cache

    def validate_port_conflict(self, config: PortConfig) -> Tuple[bool, List[str]]:
        """
        验证端口冲突

        Returns:
            (is_valid, conflict_messages)
        """
        import socket

        conflicts = []

        # 检查端口是否重复
        port_values = {
            "backend_api": config.backend_api,
            "frontend": config.frontend,
            "ocr_service": config.ocr_service,
            "postgres": config.postgres,
        }
        if config.cloud_api:
            port_values["cloud_api"] = config.cloud_api
        if config.site_hub_api:
            port_values["site_hub_api"] = config.site_hub_api
        if getattr(config, "media_proxy", None):
            port_values["media_proxy"] = config.media_proxy

        # 检查内部端口重复
        seen_ports = {}
        for service, port in port_values.items():
            if port in seen_ports:
                conflicts.append(
                    f"端口 {port} 被 {seen_ports[port]} 和 {service} 重复使用"
                )
            else:
                seen_ports[port] = service

        # 检查端口是否被占用（可选，需要权限）
        try:
            for service, port in port_values.items():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result == 0:
                    conflicts.append(f"端口 {port} ({service}) 已被占用")
        except Exception as e:
            logger.warning(f"端口占用检查失败（可能需要权限）: {e}")

        return len(conflicts) == 0, conflicts

    def update_port_config(self, config: PortConfig) -> Tuple[bool, Optional[str]]:
        """
        更新端口配置

        将配置保存到系统设置中，并返回是否需要重启服务

        Returns:
            (success, restart_message)
        """
        try:
            # 验证端口冲突
            is_valid, conflicts = self.validate_port_conflict(config)
            if not is_valid:
                error_msg = "端口配置冲突:\n" + "\n".join(conflicts)
                logger.error(error_msg)
                return False, error_msg

            # 构建作用域前缀（支持独立的环境和站点作用域）
            scope_parts = []
            if config.cluster:
                scope_parts.append(config.cluster)
            if config.environment:
                scope_parts.append(config.environment)
            if config.site:
                scope_parts.append(config.site)

            scope_prefix = ".".join(scope_parts) + "." if scope_parts else ""

            # 准备更新字典
            updates = {}
            for key, value in config.dict(exclude_none=True).items():
                # 跳过作用域字段
                if key in ["cluster", "environment", "site"]:
                    continue

                setting_key = f"system.ports.{scope_prefix}{key}"
                updates[setting_key] = str(value)

            # 批量更新设置
            settings_store.update_settings(updates)

            # 清除缓存
            self._config_cache = None
            self._cache_key = None

            logger.info(f"端口配置已更新: {config.dict()}")

            # 生成重启提示
            restart_services = []
            if config.backend_api:
                restart_services.append("后端 API")
            if config.frontend:
                restart_services.append("前端 Web Console")
            if config.ocr_service:
                restart_services.append("OCR 服务")
            if config.postgres:
                restart_services.append("PostgreSQL（需要更新连接字符串）")

            restart_message = (
                f"端口配置已保存。需要重启以下服务: {', '.join(restart_services)}"
            )
            return True, restart_message
        except Exception as e:
            logger.error(f"更新端口配置失败: {e}", exc_info=True)
            return False, str(e)

    def get_host_config(self) -> HostConfig:
        """
        获取主机名配置

        优先级:
        1. 系统设置 (system.hosts.*)
        2. 环境变量 (BACKEND_HOST, etc.)
        3. 默认值 (localhost)
        """
        host_dict = {}

        # 从系统设置读取主机名配置
        host_keys = {
            "backend_api_host": "backend_api",
            "frontend_host": "frontend",
            "ocr_service_host": "ocr_service",
            "cloud_api_host": "cloud_api",
            "site_hub_api_host": "site_hub_api",
        }

        for host_key, service_key in host_keys.items():
            setting_key = f"system.hosts.{service_key}"
            setting = settings_store.get_setting(setting_key)
            if setting and setting.value:
                host_dict[host_key] = setting.value
            else:
                # 从环境变量读取
                env_var = f"{service_key.upper()}_HOST"
                env_value = os.getenv(env_var)
                host_dict[host_key] = env_value if env_value else "localhost"

        # 读取 CORS 配置
        cors_setting = settings_store.get_setting("system.cors.origins")
        if cors_setting and cors_setting.value:
            try:
                host_dict["cors_origins"] = json.loads(cors_setting.value)
            except:
                host_dict["cors_origins"] = []
        else:
            host_dict["cors_origins"] = []

        return HostConfig(**host_dict)

    def get_service_url(
        self,
        service: str,
        cluster: Optional[str] = None,
        environment: Optional[str] = None,
        site: Optional[str] = None,
        protocol: str = "http",
    ) -> str:
        """
        获取服务 URL（自动从配置读取主机名和端口，支持作用域）

        Args:
            service: 服务名称 (backend_api, frontend, ocr_service, cloud_api, site_hub_api)
            cluster: 集群标识（可选）
            environment: 环境标识（可选）
            site: 站点标识（可选）
            protocol: 协议 (默认: http)
        """
        # 使用作用域参数获取端口配置
        config = self.get_port_config(
            cluster=cluster, environment=environment, site=site
        )
        port = getattr(config, service, None)

        if port is None:
            raise ValueError(f"未知的服务: {service}")

        # 从配置读取主机名
        host_config = self.get_host_config()
        host_key = f"{service}_host"
        host = getattr(host_config, host_key, "localhost")

        return f"{protocol}://{host}:{port}"

    def get_all_service_urls(
        self,
        cluster: Optional[str] = None,
        environment: Optional[str] = None,
        site: Optional[str] = None,
        protocol: str = "http",
    ) -> ServiceURLConfig:
        """
        获取所有服务 URL（自动从配置读取主机名）

        Args:
            cluster: 集群标识
            environment: 环境标识
            site: 站点标识
            protocol: 协议 (默认: http)
        """
        config = self.get_port_config(
            cluster=cluster, environment=environment, site=site
        )
        host_config = self.get_host_config()

        return ServiceURLConfig(
            backend_api_url=f"{protocol}://{host_config.backend_api_host}:{config.backend_api}",
            frontend_url=f"{protocol}://{host_config.frontend_host}:{config.frontend}",
            ocr_service_url=f"{protocol}://{host_config.ocr_service_host}:{config.ocr_service}",
            cloud_api_url=(
                f"{protocol}://{host_config.cloud_api_host}:{config.cloud_api}"
                if config.cloud_api and host_config.cloud_api_host
                else None
            ),
            site_hub_api_url=(
                f"{protocol}://{host_config.site_hub_api_host}:{config.site_hub_api}"
                if config.site_hub_api and host_config.site_hub_api_host
                else None
            ),
        )


# 全局单例
port_config_service = PortConfigService()

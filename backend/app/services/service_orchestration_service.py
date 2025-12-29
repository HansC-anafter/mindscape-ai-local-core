"""
服务编排服务
负责更新 docker-compose、Ingress 配置并重启服务
"""
import os
import yaml
import logging
import subprocess
from typing import Dict, List, Optional, Any
from pathlib import Path
from ..models.port_config import PortConfig, HostConfig

logger = logging.getLogger(__name__)


class ServiceOrchestrationService:
    """服务编排服务"""

    def __init__(self):
        self.compose_file = Path(os.getenv('COMPOSE_FILE', 'docker-compose.yml'))
        self.ingress_dir = Path(os.getenv('INGRESS_DIR', 'k8s/ingress'))

    def update_docker_compose(self, config: PortConfig) -> bool:
        """
        更新 docker-compose.yml 中的端口映射

        Returns:
            是否成功更新
        """
        try:
            if not self.compose_file.exists():
                logger.warning(f"docker-compose.yml 不存在: {self.compose_file}")
                return False

            with open(self.compose_file, 'r') as f:
                compose_data = yaml.safe_load(f)

            # 更新服务端口映射
            # 格式: (服务名, (配置键, 默认主机端口, 容器内固定端口, 环境变量键名))
            service_port_mapping = {
                'backend': ('backend_api', 8200, 8000, 'PORT'),  # 容器内固定 8000
                'frontend': ('frontend', 8300, 3000, 'PORT'),  # 容器内固定 3000
                'ocr-service': ('ocr_service', 8400, 8000, 'PORT'),  # 容器内固定 8000
                'postgres': ('postgres', 5440, 5432, 'POSTGRES_PORT'),  # 容器内固定 5432
                'cloud-api': ('cloud_api', 8500, 8000, 'PORT'),
                'site-hub-api': ('site_hub_api', 8102, 8000, 'PORT'),
            }

            updated = False
            for service_name, (config_key, default_host_port, container_port, env_key) in service_port_mapping.items():
                host_port = getattr(config, config_key, None)
                if host_port is None:
                    continue

                if 'services' in compose_data and service_name in compose_data['services']:
                    service = compose_data['services'][service_name]

                    # 更新端口映射格式: "host_port:container_port"
                    # 容器内端口保持固定，只更新主机端口映射

                    # 检查服务是否已有 ports 字段
                    if 'ports' in service and service['ports']:
                        # 情况 1: 服务已有 ports 字段，只更新匹配的端口映射，保留其他端口
                        port_updated = False
                        new_ports = []
                        target_mapping_added = False

                        # 如果 ports 是列表格式
                        if isinstance(service['ports'], list):
                            for port_mapping in service['ports']:
                                if isinstance(port_mapping, str):
                                    # 格式: "host_port:container_port" 或 "bind_ip:host_port:container_port"
                                    parts = port_mapping.split(':')
                                    if len(parts) == 2:
                                        # 格式: "host_port:container_port"
                                        existing_host_port, existing_container_port = parts
                                        # 只更新匹配目标容器端口的映射，保留其他端口（如调试端口）
                                        if int(existing_container_port) == container_port:
                                            # 这是我们要更新的端口映射
                                            new_ports.append(f"{host_port}:{container_port}")
                                            port_updated = True
                                            target_mapping_added = True
                                        else:
                                            # 保留其他端口映射（如调试端口 9229）
                                            new_ports.append(port_mapping)
                                    elif len(parts) == 3:
                                        # 格式: "bind_ip:host_port:container_port" (如 "127.0.0.1:8200:8000")
                                        bind_ip, existing_host_port, existing_container_port = parts
                                        # 只更新匹配目标容器端口的映射，保留绑定 IP
                                        if int(existing_container_port) == container_port:
                                            # 这是我们要更新的端口映射，保留绑定 IP
                                            new_ports.append(f"{bind_ip}:{host_port}:{container_port}")
                                            port_updated = True
                                            target_mapping_added = True
                                        else:
                                            # 保留其他端口映射
                                            new_ports.append(port_mapping)
                                    else:
                                        # 其他格式，保留原样
                                        new_ports.append(port_mapping)
                                elif isinstance(port_mapping, dict):
                                    # 格式: { "published": host_port, "target": container_port, "protocol": "tcp", "mode": "host", "host_ip": "127.0.0.1", ... }
                                    existing_target = port_mapping.get('target')
                                    if existing_target == container_port:
                                        # 这是我们要更新的端口映射
                                        # 重要：使用 copy() 保留所有原有字段（protocol, mode, host_ip 等），只更新 published
                                        # 这样可以保持负载模式、协议、绑定 IP 等配置不变
                                        updated_mapping = port_mapping.copy()
                                        updated_mapping['published'] = host_port
                                        new_ports.append(updated_mapping)
                                        port_updated = True
                                        target_mapping_added = True
                                    else:
                                        # 保留其他端口映射（不匹配目标容器端口）
                                        new_ports.append(port_mapping)
                                else:
                                    new_ports.append(port_mapping)
                        else:
                            # 如果 ports 是其他格式，创建新的映射
                            new_ports = [f"{host_port}:{container_port}"]
                            port_updated = True
                            target_mapping_added = True

                        # 如果没有找到匹配的端口映射，添加新的映射（保留现有端口）
                        if not target_mapping_added:
                            new_ports.append(f"{host_port}:{container_port}")
                            port_updated = True
                            logger.info(f"添加 {service_name} 端口映射: {host_port}:{container_port}（保留现有端口）")
                        elif port_updated:
                            logger.info(f"更新 {service_name} 端口映射: {host_port}:{container_port}（保留其他端口）")

                        if port_updated:
                            service['ports'] = new_ports
                            updated = True
                    else:
                        # 情况 2: 服务原本没有 ports 字段或 ports 为空，添加新的端口映射
                        # 这确保即使服务未定义 ports，也能添加端口映射
                        if 'ports' not in service:
                            service['ports'] = []
                        service['ports'] = [f"{host_port}:{container_port}"]
                        updated = True
                        logger.info(f"添加 {service_name} 端口映射: {host_port}:{container_port}")

                    # 更新环境变量（使用服务期望的键名）
                    if 'environment' not in service:
                        service['environment'] = {}

                    # 对于需要容器内端口的服务，同时设置容器内端口环境变量
                    if env_key == 'PORT':
                        # 服务在容器内监听 container_port
                        if service['environment'].get(env_key) != str(container_port):
                            service['environment'][env_key] = str(container_port)
                            updated = True
                    elif env_key == 'POSTGRES_PORT':
                        # PostgreSQL 使用容器内固定端口
                        if service['environment'].get(env_key) != str(container_port):
                            service['environment'][env_key] = str(container_port)
                            updated = True

                    # 可选：同时设置主机端口环境变量（如果服务需要）
                    host_port_env_key = f"{config_key.upper()}_HOST_PORT"
                    if service['environment'].get(host_port_env_key) != str(host_port):
                        service['environment'][host_port_env_key] = str(host_port)
                        updated = True

            if updated:
                # 备份原文件
                backup_file = self.compose_file.with_suffix('.yml.backup')
                with open(backup_file, 'w') as f:
                    yaml.dump(compose_data, f, default_flow_style=False)

                # 写入新配置
                with open(self.compose_file, 'w') as f:
                    yaml.dump(compose_data, f, default_flow_style=False)

                logger.info(f"docker-compose.yml 已更新")

            return True
        except Exception as e:
            logger.error(f"更新 docker-compose.yml 失败: {e}", exc_info=True)
            return False

    def update_ingress_config(self, config: PortConfig, host_config: HostConfig) -> bool:
        """
        更新 Kubernetes Ingress 配置

        Returns:
            是否成功更新
        """
        try:
            if not self.ingress_dir.exists():
                logger.warning(f"Ingress 目录不存在: {self.ingress_dir}")
                return False

            # 更新 Ingress YAML 文件
            ingress_files = list(self.ingress_dir.glob('*.yaml')) + list(self.ingress_dir.glob('*.yml'))

            for ingress_file in ingress_files:
                with open(ingress_file, 'r') as f:
                    ingress_data = yaml.safe_load(f)

                updated = False

                # 更新后端服务端口
                if 'spec' in ingress_data and 'rules' in ingress_data['spec']:
                    for rule in ingress_data['spec']['rules']:
                        if 'http' in rule and 'paths' in rule['http']:
                            for path in rule['http']['paths']:
                                backend = path.get('backend', {})
                                service = backend.get('service', {})

                                # 根据服务名称更新端口
                                service_name = service.get('name', '')
                                if 'backend' in service_name.lower():
                                    service['port'] = {'number': config.backend_api}
                                    updated = True
                                elif 'frontend' in service_name.lower():
                                    service['port'] = {'number': config.frontend}
                                    updated = True
                                elif 'ocr' in service_name.lower():
                                    service['port'] = {'number': config.ocr_service}
                                    updated = True

                if updated:
                    # 备份原文件
                    backup_file = ingress_file.with_suffix('.yaml.backup')
                    with open(backup_file, 'w') as f:
                        yaml.dump(ingress_data, f, default_flow_style=False)

                    # 写入新配置
                    with open(ingress_file, 'w') as f:
                        yaml.dump(ingress_data, f, default_flow_style=False)

                    logger.info(f"Ingress 配置已更新: {ingress_file}")

            return True
        except Exception as e:
            logger.error(f"更新 Ingress 配置失败: {e}", exc_info=True)
            return False

    def restart_services(self, services: List[str], method: str = "docker-compose") -> Dict[str, bool]:
        """
        重启服务

        Args:
            services: 服务名称列表
            method: 重启方法 (docker-compose, kubernetes, systemd)

        Returns:
            每个服务的重启结果
        """
        results = {}

        if method == "docker-compose":
            for service in services:
                try:
                    cmd = ['docker-compose', 'restart', service]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    results[service] = result.returncode == 0
                    if result.returncode != 0:
                        logger.error(f"重启 {service} 失败: {result.stderr}")
                except Exception as e:
                    logger.error(f"重启 {service} 异常: {e}", exc_info=True)
                    results[service] = False

        elif method == "kubernetes":
            for service in services:
                try:
                    # 滚动重启 Deployment
                    cmd = ['kubectl', 'rollout', 'restart', f'deployment/{service}']
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    results[service] = result.returncode == 0
                    if result.returncode != 0:
                        logger.error(f"重启 {service} 失败: {result.stderr}")
                except Exception as e:
                    logger.error(f"重启 {service} 异常: {e}", exc_info=True)
                    results[service] = False

        return results

    def apply_port_changes(self, config: PortConfig, host_config: HostConfig, auto_restart: bool = False) -> Dict[str, Any]:
        """
        应用端口变更（更新配置并可选重启服务）

        Returns:
            操作结果
        """
        results = {
            'compose_updated': False,
            'ingress_updated': False,
            'services_restarted': {},
        }

        # 更新 docker-compose
        results['compose_updated'] = self.update_docker_compose(config)

        # 更新 Ingress
        results['ingress_updated'] = self.update_ingress_config(config, host_config)

        # 可选：自动重启服务
        if auto_restart:
            services_to_restart = []
            if config.backend_api:
                services_to_restart.append('backend')
            if config.frontend:
                services_to_restart.append('frontend')
            if config.ocr_service:
                services_to_restart.append('ocr-service')

            method = os.getenv('ORCHESTRATION_METHOD', 'docker-compose')
            results['services_restarted'] = self.restart_services(services_to_restart, method=method)

        return results


# 全局单例
service_orchestration_service = ServiceOrchestrationService()


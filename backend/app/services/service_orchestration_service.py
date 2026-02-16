"""
Service Orchestration Service

Responsible for updating docker-compose, Ingress config, and restarting services.
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
    """Service orchestration service."""

    def __init__(self):
        self.compose_file = Path(os.getenv("COMPOSE_FILE", "docker-compose.yml"))
        self.ingress_dir = Path(os.getenv("INGRESS_DIR", "k8s/ingress"))

    def update_docker_compose(self, config: PortConfig) -> bool:
        """
        Update port mappings in docker-compose.yml.

        Returns:
            Whether the update succeeded
        """
        try:
            if not self.compose_file.exists():
                logger.warning(f"docker-compose.yml not found: {self.compose_file}")
                return False

            with open(self.compose_file, "r") as f:
                compose_data = yaml.safe_load(f)

            # Service port mapping
            # Format: (service_name, (config_key, default_host_port, container_port, env_var_key))
            service_port_mapping = {
                "backend": (
                    "backend_api",
                    8200,
                    8000,
                    "PORT",
                ),  # container listens on 8000
                "frontend": (
                    "frontend",
                    8300,
                    3000,
                    "PORT",
                ),  # container listens on 3000
                "ocr-service": (
                    "ocr_service",
                    8400,
                    8000,
                    "PORT",
                ),  # container listens on 8000
                "postgres": (
                    "postgres",
                    5440,
                    5432,
                    "POSTGRES_PORT",
                ),  # container listens on 5432
                "cloud-api": ("cloud_api", 8500, 8000, "PORT"),
                "cloud-provider-api": ("cloud_provider_api", 8102, 8000, "PORT"),
            }

            updated = False
            for service_name, (
                config_key,
                default_host_port,
                container_port,
                env_key,
            ) in service_port_mapping.items():
                host_port = getattr(config, config_key, None)
                if host_port is None:
                    continue

                if (
                    "services" in compose_data
                    and service_name in compose_data["services"]
                ):
                    service = compose_data["services"][service_name]

                    # Update port mapping format: "host_port:container_port"
                    # Container port stays fixed; only update host port mapping

                    # Check if service already has ports field
                    if "ports" in service and service["ports"]:
                        # Case 1: service has existing ports; update matching mappings, preserve others
                        port_updated = False
                        new_ports = []
                        target_mapping_added = False

                        # Handle list-format ports
                        if isinstance(service["ports"], list):
                            for port_mapping in service["ports"]:
                                if isinstance(port_mapping, str):
                                    # Format: "host_port:container_port" or "bind_ip:host_port:container_port"
                                    parts = port_mapping.split(":")
                                    if len(parts) == 2:
                                        # Format: "host_port:container_port"
                                        existing_host_port, existing_container_port = (
                                            parts
                                        )
                                        # Only update mappings matching target container port; preserve others (e.g. debug port)
                                        if (
                                            int(existing_container_port)
                                            == container_port
                                        ):
                                            new_ports.append(
                                                f"{host_port}:{container_port}"
                                            )
                                            port_updated = True
                                            target_mapping_added = True
                                        else:
                                            # Preserve non-matching port mappings (e.g. debug port 9229)
                                            new_ports.append(port_mapping)
                                    elif len(parts) == 3:
                                        # Format: "bind_ip:host_port:container_port" (e.g. "127.0.0.1:8200:8000")
                                        (
                                            bind_ip,
                                            existing_host_port,
                                            existing_container_port,
                                        ) = parts
                                        # Only update mappings matching target container port; preserve bind IP
                                        if (
                                            int(existing_container_port)
                                            == container_port
                                        ):
                                            new_ports.append(
                                                f"{bind_ip}:{host_port}:{container_port}"
                                            )
                                            port_updated = True
                                            target_mapping_added = True
                                        else:
                                            new_ports.append(port_mapping)
                                    else:
                                        # Unknown format; preserve as-is
                                        new_ports.append(port_mapping)
                                elif isinstance(port_mapping, dict):
                                    # Format: { "published": host_port, "target": container_port, "protocol": "tcp", ... }
                                    existing_target = port_mapping.get("target")
                                    if existing_target == container_port:
                                        # Update published port; preserve all other fields (protocol, mode, host_ip)
                                        updated_mapping = port_mapping.copy()
                                        updated_mapping["published"] = host_port
                                        new_ports.append(updated_mapping)
                                        port_updated = True
                                        target_mapping_added = True
                                    else:
                                        new_ports.append(port_mapping)
                                else:
                                    new_ports.append(port_mapping)
                        else:
                            # Non-list ports format; create new mapping
                            new_ports = [f"{host_port}:{container_port}"]
                            port_updated = True
                            target_mapping_added = True

                        # If no matching port mapping found, add new one (preserve existing ports)
                        if not target_mapping_added:
                            new_ports.append(f"{host_port}:{container_port}")
                            port_updated = True
                            logger.info(
                                f"Added {service_name} port mapping: {host_port}:{container_port} (existing ports preserved)"
                            )
                        elif port_updated:
                            logger.info(
                                f"Updated {service_name} port mapping: {host_port}:{container_port} (other ports preserved)"
                            )

                        if port_updated:
                            service["ports"] = new_ports
                            updated = True
                    else:
                        # Case 2: service has no ports field or ports is empty; add new mapping
                        if "ports" not in service:
                            service["ports"] = []
                        service["ports"] = [f"{host_port}:{container_port}"]
                        updated = True
                        logger.info(
                            f"Added {service_name} port mapping: {host_port}:{container_port}"
                        )

                    # Update environment variables (use the key name the service expects)
                    if "environment" not in service:
                        service["environment"] = {}

                    # For services needing in-container port, set container port env var
                    if env_key == "PORT":
                        # Service listens on container_port inside the container
                        if service["environment"].get(env_key) != str(container_port):
                            service["environment"][env_key] = str(container_port)
                            updated = True
                    elif env_key == "POSTGRES_PORT":
                        # PostgreSQL uses fixed container port
                        if service["environment"].get(env_key) != str(container_port):
                            service["environment"][env_key] = str(container_port)
                            updated = True

                    # Optionally set host port env var (if service needs it)
                    host_port_env_key = f"{config_key.upper()}_HOST_PORT"
                    if service["environment"].get(host_port_env_key) != str(host_port):
                        service["environment"][host_port_env_key] = str(host_port)
                        updated = True

            if updated:
                # Back up original file
                backup_file = self.compose_file.with_suffix(".yml.backup")
                with open(backup_file, "w") as f:
                    yaml.dump(compose_data, f, default_flow_style=False)

                # Write new config
                with open(self.compose_file, "w") as f:
                    yaml.dump(compose_data, f, default_flow_style=False)

                logger.info("docker-compose.yml updated")

            return True
        except Exception as e:
            logger.error(f"Failed to update docker-compose.yml: {e}", exc_info=True)
            return False

    def update_ingress_config(
        self, config: PortConfig, host_config: HostConfig
    ) -> bool:
        """
        Update Kubernetes Ingress configuration.

        Returns:
            Whether the update succeeded
        """
        try:
            if not self.ingress_dir.exists():
                logger.warning(f"Ingress directory not found: {self.ingress_dir}")
                return False

            # Update Ingress YAML files
            ingress_files = list(self.ingress_dir.glob("*.yaml")) + list(
                self.ingress_dir.glob("*.yml")
            )

            for ingress_file in ingress_files:
                with open(ingress_file, "r") as f:
                    ingress_data = yaml.safe_load(f)

                updated = False

                # Update backend service ports
                if "spec" in ingress_data and "rules" in ingress_data["spec"]:
                    for rule in ingress_data["spec"]["rules"]:
                        if "http" in rule and "paths" in rule["http"]:
                            for path in rule["http"]["paths"]:
                                backend = path.get("backend", {})
                                service = backend.get("service", {})

                                # Update port by service name
                                service_name = service.get("name", "")
                                if "backend" in service_name.lower():
                                    service["port"] = {"number": config.backend_api}
                                    updated = True
                                elif "frontend" in service_name.lower():
                                    service["port"] = {"number": config.frontend}
                                    updated = True
                                elif "ocr" in service_name.lower():
                                    service["port"] = {"number": config.ocr_service}
                                    updated = True

                if updated:
                    # Back up original file
                    backup_file = ingress_file.with_suffix(".yaml.backup")
                    with open(backup_file, "w") as f:
                        yaml.dump(ingress_data, f, default_flow_style=False)

                    # Write new config
                    with open(ingress_file, "w") as f:
                        yaml.dump(ingress_data, f, default_flow_style=False)

                    logger.info(f"Ingress config updated: {ingress_file}")

            return True
        except Exception as e:
            logger.error(f"Failed to update Ingress config: {e}", exc_info=True)
            return False

    def restart_services(
        self, services: List[str], method: str = "docker-compose"
    ) -> Dict[str, bool]:
        """
        Restart services.

        Args:
            services: List of service names
            method: Restart method (docker-compose, kubernetes, systemd)

        Returns:
            Restart result per service
        """
        results = {}

        if method == "docker-compose":
            for service in services:
                try:
                    cmd = ["docker-compose", "restart", service]
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=60
                    )
                    results[service] = result.returncode == 0
                    if result.returncode != 0:
                        logger.error(f"Failed to restart {service}: {result.stderr}")
                except Exception as e:
                    logger.error(f"Error restarting {service}: {e}", exc_info=True)
                    results[service] = False

        elif method == "kubernetes":
            for service in services:
                try:
                    # Rolling restart of Deployment
                    cmd = ["kubectl", "rollout", "restart", f"deployment/{service}"]
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=120
                    )
                    results[service] = result.returncode == 0
                    if result.returncode != 0:
                        logger.error(f"Failed to restart {service}: {result.stderr}")
                except Exception as e:
                    logger.error(f"Error restarting {service}: {e}", exc_info=True)
                    results[service] = False

        return results

    def apply_port_changes(
        self, config: PortConfig, host_config: HostConfig, auto_restart: bool = False
    ) -> Dict[str, Any]:
        """
        Apply port changes (update config and optionally restart services).

        Returns:
            Operation results
        """
        results = {
            "compose_updated": False,
            "ingress_updated": False,
            "services_restarted": {},
        }

        # Update docker-compose
        results["compose_updated"] = self.update_docker_compose(config)

        # Update Ingress
        results["ingress_updated"] = self.update_ingress_config(config, host_config)

        # Optionally auto-restart services
        if auto_restart:
            services_to_restart = []
            if config.backend_api:
                services_to_restart.append("backend")
            if config.frontend:
                services_to_restart.append("frontend")
            if config.ocr_service:
                services_to_restart.append("ocr-service")

            method = os.getenv("ORCHESTRATION_METHOD", "docker-compose")
            results["services_restarted"] = self.restart_services(
                services_to_restart, method=method
            )

        return results


# Global singleton
service_orchestration_service = ServiceOrchestrationService()

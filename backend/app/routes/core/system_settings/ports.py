"""
端口配置 API
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
import logging

from backend.app.models.port_config import PortConfig, ServiceURLConfig
from backend.app.services.port_config_service import port_config_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ports", tags=["ports"])


@router.get("/", response_model=PortConfig)
async def get_port_config(
    cluster: Optional[str] = Query(None, description="集群标识"),
    environment: Optional[str] = Query(None, description="环境标识"),
    site: Optional[str] = Query(None, description="站点标识")
):
    """
    获取端口配置

    Args:
        cluster: 集群标识（可选）
        environment: 环境标识（可选）
        site: 站点标识（可选）
    """
    try:
        return port_config_service.get_port_config(
            cluster=cluster,
            environment=environment,
            site=site
        )
    except Exception as e:
        logger.error(f"获取端口配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取端口配置失败: {str(e)}")


@router.put("/", response_model=Dict[str, Any])
async def update_port_config(
    config: PortConfig,
    auto_apply: bool = Query(False, description="是否自动应用变更（更新 docker-compose/Ingress）"),
    auto_restart: bool = Query(False, description="是否自动重启服务（需要 auto_apply=True）")
):
    """
    更新端口配置

    Args:
        config: 端口配置
        auto_apply: 是否自动应用变更（更新 docker-compose/Ingress）
        auto_restart: 是否自动重启服务（需要 auto_apply=True）
    """
    try:
        # 验证端口冲突
        is_valid, conflicts = port_config_service.validate_port_conflict(config)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "端口配置冲突",
                    "conflicts": conflicts
                }
            )

        # 更新配置
        success, message = port_config_service.update_port_config(config)
        if not success:
            raise HTTPException(status_code=500, detail=message or "更新端口配置失败")

        result = {
            "success": True,
            "message": message or "端口配置已更新",
            "config": port_config_service.get_port_config(
                cluster=config.cluster,
                environment=config.environment,
                site=config.site
            ).dict()
        }

        # 如果启用自动应用
        if auto_apply:
            try:
                from backend.app.services.service_orchestration_service import service_orchestration_service
                host_config = port_config_service.get_host_config()
                orchestration_results = service_orchestration_service.apply_port_changes(
                    config,
                    host_config,
                    auto_restart=auto_restart
                )
                result["orchestration"] = orchestration_results
            except Exception as e:
                logger.warning(f"自动应用端口变更失败: {e}", exc_info=True)
                result["orchestration"] = {"error": f"自动应用失败: {str(e)}"}

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新端口配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新端口配置失败: {str(e)}")


@router.post("/validate", response_model=Dict[str, Any])
async def validate_port_config(config: PortConfig):
    """验证端口配置（检查冲突）"""
    try:
        is_valid, conflicts = port_config_service.validate_port_conflict(config)
        return {
            "valid": is_valid,
            "conflicts": conflicts
        }
    except Exception as e:
        logger.error(f"验证端口配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"验证端口配置失败: {str(e)}")


@router.get("/urls", response_model=ServiceURLConfig)
async def get_service_urls(
    cluster: Optional[str] = Query(None, description="集群标识"),
    environment: Optional[str] = Query(None, description="环境标识"),
    site: Optional[str] = Query(None, description="站点标识"),
    protocol: str = Query("http", description="协议")
):
    """
    获取所有服务 URL（自动从配置读取主机名）

    Args:
        cluster: 集群标识（可选）
        environment: 环境标识（可选）
        site: 站点标识（可选）
        protocol: 协议 (默认: http)
    """
    try:
        return port_config_service.get_all_service_urls(
            cluster=cluster,
            environment=environment,
            site=site,
            protocol=protocol
        )
    except Exception as e:
        logger.error(f"获取服务 URL 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取服务 URL 失败: {str(e)}")


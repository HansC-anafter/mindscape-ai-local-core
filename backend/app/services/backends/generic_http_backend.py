"""
Generic HTTP Backend

執行 Agent 通過調用遠端 HTTP 服務。

設計原則：
- 平台中立：不綁定特定服務（CRS-Hub、LangGraph Cloud、自建服務都可用）
- 協議抽象：支持多種協議格式
- 擴展友好：Console-Kit 可提供預設配置，不修改 Core

用途：
- 調用任何符合協議的遠端 Agent 服務
- 支持 Console-Kit CRS-Hub
- 支持 LangGraph Cloud
- 支持自定義 Agent 服務器
- 支持 MCP Server (通過 HTTP 包裝)
"""

import os
import aiohttp
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from backend.app.services.agent_backend import AgentBackend
from backend.app.models.mindscape import (
    MindscapeProfile, IntentCard, AgentResponse
)

logger = logging.getLogger(__name__)


class GenericHTTPBackend(AgentBackend):
    """
    通用 HTTP Backend

    特性：
    - 不綁定任何特定平台
    - 支持自定義端點和協議
    - Console-Kit CRS-Hub 只是其中一種使用方式
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        endpoint: str = "/api/run_simple",
        protocol: str = "generic"  # "generic" | "openai-like" | "langchain-like"
    ):
        """
        初始化通用 HTTP Backend

        Args:
            base_url: 遠端服務 URL（平台中立）
            api_token: API Token
            endpoint: 執行端點（默認 /api/run_simple）
            protocol: 協議類型（用於適配不同的請求/響應格式）
        """
        self.base_url = (base_url or "").rstrip("/")
        self.api_token = api_token or ""
        self.endpoint = endpoint
        self.protocol = protocol

    async def run_agent(
        self,
        task: str,
        agent_type: str,
        profile: Optional[MindscapeProfile] = None,
        active_intents: Optional[List[IntentCard]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """執行 Agent 通過調用遠端 HTTP 服務"""

        if not self.is_available():
            raise Exception(
                "Remote agent service not configured. "
                "Please configure remote backend in Settings."
            )

        # 準備請求 payload（通用格式）
        payload = {
            "task": task,
            "agent_type": agent_type,
            "mindscape_snapshot": {
                "profile": profile.dict() if profile else None,
                "active_intents": [intent.dict() for intent in (active_intents or [])]
            },
            "metadata": metadata or {}
        }

        # 調用遠端端點
        url = urljoin(self.base_url, self.endpoint)
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(
                            f"Remote service error: {response.status} - {error_text}"
                        )

                    result = await response.json()

                    # 轉換為 AgentResponse
                    return AgentResponse(
                        execution_id=result.get("execution_id", ""),
                        status=result.get("status", "completed"),
                        output=result.get("output"),
                        error_message=result.get("error_message"),
                        used_profile=result.get("used_profile"),
                        used_intents=result.get("used_intents"),
                        metadata={
                            "agent_type": agent_type,
                            "backend": "http_remote",
                            "backend_url": self.base_url,
                            "protocol": self.protocol,
                            **(metadata or {})
                        }
                    )

        except aiohttp.ClientError as e:
            logger.error(f"Remote service connection error: {e}")
            raise Exception(f"Failed to connect to remote service: {str(e)}")
        except Exception as e:
            logger.error(f"Remote service error: {e}")
            raise

    def is_available(self) -> bool:
        """檢查遠端服務是否已配置"""
        return bool(self.base_url and self.api_token)

    def get_backend_info(self) -> Dict[str, Any]:
        """獲取後端信息"""
        return {
            "type": "http_remote",
            "name": "Remote Agent Service",
            "description": "Execute agents using a remote HTTP service",
            "available": self.is_available(),
            "base_url": self.base_url if self.is_available() else None,
            "protocol": self.protocol
        }

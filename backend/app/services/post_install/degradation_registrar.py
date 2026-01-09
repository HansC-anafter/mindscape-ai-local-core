"""
Degradation Registrar

注册能力降级状态
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class DegradationRegistrar:
    """注册能力降级状态"""

    def register_degradation_status(
        self,
        capability_code: str,
        manifest: Dict,
        missing_required: List[str],
        missing_optional: List[str],
        degraded_features_map: Dict[str, List[str]],
        result
    ):
        """
        注册能力降级状态

        Args:
            capability_code: 能力代码
            manifest: 解析后的 manifest 字典
            missing_required: 缺失的必需依赖列表
            missing_optional: 缺失的可选依赖列表
            degraded_features_map: 依赖 -> 降级功能映射
            result: InstallResult 对象
        """
        try:
            from mindscape.runtime.degradation import DegradationRegistry

            # Collect all features from manifest
            all_features = []

            # Features from playbooks
            playbooks = manifest.get('playbooks', [])
            for pb in playbooks:
                pb_code = pb.get('code', '')
                if pb_code:
                    all_features.append(pb_code)

            # Features from tools
            tools = manifest.get('tools', [])
            for tool in tools:
                tool_name = tool.get('name', '')
                if tool_name:
                    all_features.append(tool_name)

            # Register with degradation registry
            registry = DegradationRegistry()
            cap_status = registry.register_capability(
                code=capability_code,
                all_features=all_features,
                missing_deps=missing_required + missing_optional,
                degraded_features_map=degraded_features_map
            )

            # Add to result
            result.degradation_status = cap_status.to_dict()
            logger.info(
                f"Registered degradation status for {capability_code}: "
                f"status={cap_status.status}, "
                f"degraded_features={cap_status.degraded_features}"
            )

        except ImportError:
            logger.warning("DegradationRegistry not available, skipping degradation registration")
            result.add_warning("Degradation status not registered (DegradationRegistry not available)")
        except Exception as e:
            logger.warning(f"Failed to register degradation status: {e}")
            result.add_warning(f"Failed to register degradation status: {e}")


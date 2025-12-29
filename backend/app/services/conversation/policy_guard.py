"""
Policy Guard - Server-side gate for tool call enforcement

Ensures Runtime Profile policies are "contracts" rather than just "hints to the model".
This is a mandatory part of MVP.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import uuid
from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tool_policy_resolver import ToolPolicyResolver, ToolPolicyInfo
from backend.app.models.mindscape import MindEvent, EventType, EventActor
import logging

logger = logging.getLogger(__name__)


@dataclass
class PolicyCheckResult:
    """Result of policy check"""
    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    proposed_action: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None


class PolicyGuard:
    """
    Policy Guard - 執行層面的政策守衛（MVP 必須做）

    統一策略：使用 ToolPolicyResolver 解析 tool_id → capability_code → risk_class
    包含 fallback 推斷和 strict_mode 缺省策略
    """

    def __init__(
        self,
        strict_mode: bool = True,
        tool_registry: Optional[ToolRegistryService] = None,
        tool_policy_resolver: Optional[ToolPolicyResolver] = None
    ):
        """
        支持惰性初始化：允許 tool_registry 和 tool_policy_resolver 皆為 None

        Args:
            strict_mode: 缺省策略（True=拒絕缺少字段的工具，False=允許但記錄警告）
            tool_registry: Tool Registry（如果提供，會用於創建 ToolPolicyResolver）
            tool_policy_resolver: ToolPolicyResolver 實例（如果 None 且 tool_registry 提供，會自動創建）

        注意：如果兩者皆為 None，會在 check_tool_call 時使用傳入的 tool_registry 創建 resolver（惰性初始化）
        """
        self.strict_mode = strict_mode
        if tool_policy_resolver:
            self.resolver = tool_policy_resolver
        elif tool_registry:
            self.resolver = ToolPolicyResolver(tool_registry)
        else:
            # 允許兩者皆為 None，支持惰性初始化
            self.resolver = None

    def check_tool_call(
        self,
        tool_id: str,
        runtime_profile: WorkspaceRuntimeProfile,
        tool_call_params: Dict[str, Any],
        tool_registry: ToolRegistryService,
        execution_id: Optional[str] = None,
        previous_tool_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        event_store: Optional[Any] = None
    ) -> PolicyCheckResult:
        """
        檢查工具調用是否符合 Runtime Profile 政策

        統一策略：使用 ToolPolicyResolver 解析（包含 fallback 推斷）

        注意：如果 PolicyGuard 初始化時沒有提供 tool_registry，會使用 check_tool_call 傳入的 tool_registry 創建 resolver

        Args:
            tool_id: 執行實例的 tool_id（一次性 call）
            runtime_profile: Runtime Profile 配置
            tool_call_params: 工具調用參數
            tool_registry: Tool Registry（用於解析 tool_id → capability_code，如果 resolver 未初始化則用於創建）
            execution_id: Execution ID（用於事件記錄）
            previous_tool_id: Previous tool ID（用於 chain length 檢查）
            workspace_id: Workspace ID（用於事件記錄）
            profile_id: Profile ID（用於事件記錄）
            event_store: Optional event store for recording events

        Returns:
            PolicyCheckResult: {
                "allowed": bool,
                "requires_approval": bool,
                "reason": str,
                "proposed_action": Optional[Dict],
                "user_message": Optional[str]  # 給用戶的提示信息
            }
        """
        # 1. 確保 resolver 已初始化（惰性初始化）
        if not hasattr(self, 'resolver') or self.resolver is None:
            if tool_registry is None:
                raise ValueError(
                    "PolicyGuard requires either tool_registry in __init__ or tool_registry in check_tool_call"
                )
            # 使用傳入的 tool_registry 創建 resolver（惰性初始化）
            self.resolver = ToolPolicyResolver(tool_registry)

        # 2. 使用 ToolPolicyResolver 解析 policy info（包含 fallback）
        policy_info = self.resolver.resolve_policy_info(tool_id)

        if not policy_info:
            if self.strict_mode:
                result = PolicyCheckResult(
                    allowed=False,
                    reason="Tool not found in registry",
                    user_message="工具未在註冊表中找到，無法執行"
                )
            else:
                logger.warning(f"Tool {tool_id} not found, allowing with warning")
                result = PolicyCheckResult(
                    allowed=True,
                    requires_approval=True,
                    reason="Tool not found in registry",
                    user_message="工具未在註冊表中找到，已允許但需要確認"
                )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=None,
                risk_class=None,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result

        capability_code = policy_info.capability_code
        risk_class = policy_info.risk_class

        # 3. 檢查是否缺少必要字段（fallback 推斷後仍為 unknown）
        if not capability_code or capability_code == "unknown":
            if self.strict_mode:
                result = PolicyCheckResult(
                    allowed=False,
                    reason=f"Tool {tool_id} missing capability_code",
                    user_message=f"工具 {tool_id} 缺少 capability_code，無法執行"
                )
            else:
                logger.warning(f"Tool {tool_id} missing capability_code, allowing with approval")
                result = PolicyCheckResult(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Tool {tool_id} missing capability_code",
                    user_message=f"工具 {tool_id} 缺少 capability_code，已允許但需要確認"
                )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result

        # 4. 檢查 allowlist/denylist（比對 capability_code）
        tool_policy = runtime_profile.tool_policy

        if tool_policy.denylist and capability_code in tool_policy.denylist:
            result = PolicyCheckResult(
                allowed=False,
                reason=f"Capability {capability_code} is in denylist",
                user_message=f"工具 {capability_code} 已被工作區政策禁止使用"
            )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result

        if tool_policy.allowlist and capability_code not in tool_policy.allowlist:
            result = PolicyCheckResult(
                allowed=False,
                reason=f"Capability {capability_code} is not in allowlist",
                user_message=f"工具 {capability_code} 不在工作區允許的工具列表中"
            )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result

        # 5. 檢查 require_approval_for_capabilities（階段 2 擴展）
        tool_policy = runtime_profile.tool_policy
        if capability_code in tool_policy.require_approval_for_capabilities:
            result = PolicyCheckResult(
                allowed=True,
                requires_approval=True,
                proposed_action=self._build_proposed_action(tool_id, tool_call_params, risk_class),
                reason=f"Capability {capability_code} requires explicit approval (require_approval_for_capabilities)",
                user_message=f"工具 {capability_code} 需要明確確認（工作區政策要求）"
            )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result

        # 6. 檢查 tool call chain length（階段 2 擴展：max_tool_call_chain）
        if execution_id and previous_tool_id:
            from backend.app.services.conversation.tool_call_chain_tracker import get_chain_tracker
            chain_tracker = get_chain_tracker(execution_id)
            chain_length = chain_tracker.get_chain_length(previous_tool_id) + 1

            if chain_length > tool_policy.max_tool_call_chain:
                result = PolicyCheckResult(
                    allowed=False,
                    reason=f"Tool call chain length ({chain_length}) exceeds maximum ({tool_policy.max_tool_call_chain})",
                    user_message=f"工具調用鏈長度 ({chain_length}) 超過最大限制 ({tool_policy.max_tool_call_chain})，請簡化操作流程"
                )
                self._record_policy_check_event(
                    tool_id=tool_id,
                    capability_code=capability_code,
                    risk_class=risk_class,
                    result=result,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    event_store=event_store
                )
                return result

        # 7. 檢查風險等級並套用 ConfirmationPolicy
        confirmation_policy = runtime_profile.confirmation_policy

        if risk_class == "external_write" and confirmation_policy.confirm_external_write:
            result = PolicyCheckResult(
                allowed=True,
                requires_approval=True,
                proposed_action=self._build_proposed_action(tool_id, tool_call_params, risk_class),
                reason=f"Tool {capability_code} requires approval (risk_class: {risk_class})",
                user_message=f"工具 {capability_code} 需要確認（風險等級：{risk_class}）"
            )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result
        elif risk_class == "soft_write" and confirmation_policy.confirm_soft_write:
            result = PolicyCheckResult(
                allowed=True,
                requires_approval=True,
                proposed_action=self._build_proposed_action(tool_id, tool_call_params, risk_class),
                reason=f"Tool {capability_code} requires approval (risk_class: {risk_class})",
                user_message=f"工具 {capability_code} 需要確認（風險等級：{risk_class}）"
            )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result

        # 8. Read-only operations are auto-allowed (if auto_read is True)
        if risk_class == "readonly" and confirmation_policy.auto_read:
            result = PolicyCheckResult(
                allowed=True,
                requires_approval=False,
                reason="Read-only operation, auto-allowed"
            )
            self._record_policy_check_event(
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store
            )
            return result

        # Default: allow (if no specific policy applies)
        result = PolicyCheckResult(
            allowed=True,
            requires_approval=False,
            reason="No policy restrictions apply"
        )

        # Record policy check event (P1: Observability)
        self._record_policy_check_event(
            tool_id=tool_id,
            capability_code=capability_code if policy_info else None,
            risk_class=risk_class if policy_info else None,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store
        )

        return result

    def _build_proposed_action(
        self,
        tool_id: str,
        tool_call_params: Dict[str, Any],
        risk_class: str
    ) -> Dict[str, Any]:
        """
        Build proposed action for user confirmation

        Args:
            tool_id: Tool ID
            tool_call_params: Tool call parameters
            risk_class: Risk class

        Returns:
            Proposed action dict
        """
        return {
            "tool_id": tool_id,
            "params": tool_call_params,
            "risk_class": risk_class,
            "requires_confirmation": True
        }

    def _record_policy_check_event(
        self,
        tool_id: str,
        capability_code: Optional[str],
        risk_class: Optional[str],
        result: PolicyCheckResult,
        execution_id: Optional[str],
        workspace_id: Optional[str],
        profile_id: Optional[str],
        event_store: Optional[Any]
    ):
        """
        Record policy check event for observability (P1)

        Args:
            tool_id: Tool ID
            capability_code: Capability code
            risk_class: Risk class
            result: Policy check result
            execution_id: Execution ID
            workspace_id: Workspace ID
            profile_id: Profile ID
            event_store: Event store instance
        """
        if not event_store or not execution_id:
            # Skip event recording if event_store or execution_id not provided
            return

        try:
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.SYSTEM,
                channel="runtime_profile",
                profile_id=profile_id or "system",
                workspace_id=workspace_id,
                event_type=EventType.POLICY_CHECK,
                payload={
                    "execution_id": execution_id,
                    "tool_id": tool_id,
                    "capability_code": capability_code,
                    "risk_class": risk_class,
                    "allowed": result.allowed,
                    "requires_approval": result.requires_approval,
                    "reason": result.reason,
                    "user_message": result.user_message
                }
            )
            event_store.create(event)
            logger.debug(f"PolicyGuard: Recorded policy check event for tool_id={tool_id}, execution_id={execution_id}, allowed={result.allowed}")
        except Exception as e:
            # Don't fail policy check if event recording fails
            logger.warning(f"Failed to record policy check event: {e}", exc_info=True)


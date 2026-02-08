"""
Settings Configuration Assistant API

Provides chat-based assistance for system configuration.
Uses intelligent model selection with fallback chain:
1. OpenAI o3/o4-mini (Thinking models)
2. Google Gemini 2.5 Pro
3. Anthropic Claude 3.5 Sonnet
4. OpenAI GPT-4o
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from backend.app.shared.llm_provider_helper import (
    create_llm_provider_manager,
    get_model_name_from_chat_model,
)
from .shared import settings_store

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================


class AssistantChatContext(BaseModel):
    """Context for the assistant chat"""

    current_tab: Optional[str] = None
    current_section: Optional[str] = None
    config_snapshot: Optional[Dict[str, Any]] = None
    governance: Optional[Dict[str, Any]] = None


class AssistantChatRequest(BaseModel):
    """Request for assistant chat"""

    message: str = Field(..., description="User message")
    context: Optional[AssistantChatContext] = None
    system_prompt: Optional[str] = None


class AssistantAction(BaseModel):
    """Action that the assistant can suggest"""

    label: str
    action: str
    params: Optional[Dict[str, Any]] = None


class AssistantChatResponse(BaseModel):
    """Response from assistant chat"""

    response: str
    actions: List[AssistantAction] = Field(default_factory=list)
    model_used: Optional[str] = None


# ============================================================
# Model Selection Logic
# ============================================================

# Thinking models preferred for complex reasoning tasks
THINKING_MODELS = [
    "o3",
    "o4-mini",
    "o1",
    "o1-mini",
]

# Fallback chain for model selection
FALLBACK_CHAIN = [
    ("openai", "o3"),
    ("openai", "o4-mini"),
    ("openai", "o1"),
    ("vertex-ai", "gemini-2.5-pro"),
    ("vertex-ai", "gemini-2.0-flash"),
    ("anthropic", "claude-3-5-sonnet"),
    ("openai", "gpt-4o"),
    ("openai", "gpt-4o-mini"),
]

NO_MODEL_GUIDE_MESSAGE = """
## 🔑 需要設定 AI 模型

您尚未配置任何 LLM API Key，配置助手需要 AI 模型來協助您。

### 最快方式：使用 Google Gemini (免費)

1. 前往 [Google AI Studio](https://aistudio.google.com/apikey)
2. 使用 Google 帳號登入
3. 點擊「Create API Key」
4. 複製 API Key 並儲存到設定

### 其他選項
- OpenAI: 需要付費帳戶
- Anthropic: 需要付費帳戶

點擊下方按鈕開始設定！
"""


def get_available_providers() -> Dict[str, bool]:
    """Check which LLM providers are available"""
    try:
        llm_manager = create_llm_provider_manager()
        available = llm_manager.get_available_providers()
        return {
            "openai": "openai" in available,
            "anthropic": "anthropic" in available,
            "vertex-ai": "vertex-ai" in available,
            "ollama": "ollama" in available,
        }
    except Exception as e:
        logger.error(f"Error checking available providers: {e}")
        return {
            "openai": False,
            "anthropic": False,
            "vertex-ai": False,
            "ollama": False,
        }


def select_best_model(available_providers: Dict[str, bool]) -> Optional[tuple]:
    """
    Select the best available model based on fallback chain

    Returns:
        (provider, model) tuple or None if no model available
    """
    for provider, model in FALLBACK_CHAIN:
        if available_providers.get(provider, False):
            return (provider, model)
    return None


def build_assistant_system_prompt(
    base_prompt: Optional[str], context: Optional[AssistantChatContext]
) -> str:
    """Build enhanced system prompt for the assistant"""

    if base_prompt:
        enhanced = base_prompt
    else:
        enhanced = """You are a configuration assistant for Mindscape AI Local Core.
Your role is to help users configure their system, including:
- Setting up LLM API keys
- Configuring external agents
- Managing AI team governance
- Diagnosing configuration issues

Be concise, helpful, and action-oriented."""

    # Add context-specific instructions
    if context:
        enhanced += f"""

## Current Context
- Tab: {context.current_tab or 'unknown'}
- Section: {context.current_section or 'none'}
"""

        if context.current_tab == "ai-team-governance":
            enhanced += """
## AI Team Governance Context
You are helping with AI Team Governance settings:
- Install Agents: Help users install and configure external AI agents
- Model Policy: Help users set up model usage policies

For agent installation:
1. Check if required CLI tools are installed
2. Guide users through the installation process
3. Help configure the agent after installation
"""

        if context.governance:
            enhanced += f"""
Governance state: {json.dumps(context.governance, ensure_ascii=False)}
"""

    # Add action format instructions
    enhanced += """

## Response Format
When you want to suggest actions, include them in a JSON block at the end of your response:

```actions
[
  {"label": "Button Text", "action": "navigate", "params": {"tab": "basic"}},
  {"label": "Open Link", "action": "open_url", "params": {"url": "https://example.com"}}
]
```

Available actions:
- navigate: Navigate to a settings tab/section
- open_url: Open an external URL
- check_cli: Check if a CLI tool is installed (params: {tool: "openclaw"})
- refresh: Refresh the current page
"""

    return enhanced


def parse_actions_from_response(response_text: str) -> tuple:
    """
    Parse actions from the response text

    Returns:
        (clean_response, actions_list)
    """
    actions = []
    clean_response = response_text

    # Look for ```actions block
    action_pattern = r"```actions\s*([\s\S]*?)\s*```"
    matches = re.findall(action_pattern, response_text)

    if matches:
        for match in matches:
            try:
                parsed = json.loads(match)
                if isinstance(parsed, list):
                    for action in parsed:
                        if (
                            isinstance(action, dict)
                            and "label" in action
                            and "action" in action
                        ):
                            actions.append(
                                AssistantAction(
                                    label=action["label"],
                                    action=action["action"],
                                    params=action.get("params"),
                                )
                            )
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse actions JSON: {match}")

        # Remove the actions block from the response
        clean_response = re.sub(action_pattern, "", response_text).strip()

    return clean_response, actions


# ============================================================
# API Endpoints
# ============================================================


@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(request: AssistantChatRequest) -> AssistantChatResponse:
    """
    Chat with the configuration assistant

    Uses intelligent model selection with fallback chain.
    If no LLM is configured, returns guidance on how to set up.
    """
    try:
        # Check available providers
        available_providers = get_available_providers()

        # Check if any provider is available
        if not any(available_providers.values()):
            # No LLM configured, return guidance
            return AssistantChatResponse(
                response=NO_MODEL_GUIDE_MESSAGE,
                actions=[
                    AssistantAction(
                        label="🔑 設定 Google Gemini (免費)",
                        action="open_url",
                        params={"url": "https://aistudio.google.com/apikey"},
                    ),
                    AssistantAction(
                        label="⚙️ 前往 LLM 設定",
                        action="navigate",
                        params={"tab": "basic", "section": "llm-api-keys"},
                    ),
                ],
                model_used=None,
            )

        # Select best available model
        selection = select_best_model(available_providers)
        if not selection:
            return AssistantChatResponse(
                response="無法找到可用的 LLM 模型。請配置至少一個 LLM API Key。",
                actions=[
                    AssistantAction(
                        label="前往設定", action="navigate", params={"tab": "basic"}
                    )
                ],
                model_used=None,
            )

        provider, model = selection
        logger.info(f"Using model: {provider}/{model}")

        # Create LLM manager and get provider
        llm_manager = create_llm_provider_manager()
        llm_provider = llm_manager.get_provider(provider)

        if not llm_provider:
            raise HTTPException(
                status_code=500, detail=f"Failed to get LLM provider: {provider}"
            )

        # Build system prompt
        system_prompt = build_assistant_system_prompt(
            request.system_prompt, request.context
        )

        # Prepare messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message},
        ]

        # Call LLM
        response = await llm_provider.chat_completion(
            messages=messages, model=model, temperature=0.7, max_tokens=2000
        )

        # Extract response text
        response_text = (
            response.get("content", "") if isinstance(response, dict) else str(response)
        )

        # Parse actions from response
        clean_response, actions = parse_actions_from_response(response_text)

        return AssistantChatResponse(
            response=clean_response, actions=actions, model_used=f"{provider}/{model}"
        )

    except Exception as e:
        logger.error(f"Error in assistant chat: {e}", exc_info=True)
        return AssistantChatResponse(
            response=f"發生錯誤：{str(e)}\n\n請確認 LLM API Key 已正確配置。",
            actions=[
                AssistantAction(
                    label="檢查設定", action="navigate", params={"tab": "basic"}
                )
            ],
            model_used=None,
        )


@router.get("/assistant/status")
async def get_assistant_status() -> Dict[str, Any]:
    """
    Get the status of the configuration assistant

    Returns available providers and recommended model.
    """
    available_providers = get_available_providers()
    selection = select_best_model(available_providers)

    return {
        "available": any(available_providers.values()),
        "providers": available_providers,
        "recommended_model": f"{selection[0]}/{selection[1]}" if selection else None,
        "fallback_chain": [f"{p}/{m}" for p, m in FALLBACK_CHAIN],
    }


# ============================================================
# Agent Mode Endpoint
# ============================================================


class AgentChatRequest(BaseModel):
    """Request for agent mode chat"""

    message: str = Field(..., description="User message/task")
    context: Optional[AssistantChatContext] = None
    max_iterations: int = Field(
        default=5, ge=1, le=10, description="Max agent iterations"
    )


class AgentStepInfo(BaseModel):
    """Information about a single agent step"""

    step_number: int
    thought: str
    action: Optional[str] = None
    action_result: Optional[str] = None
    success: Optional[bool] = None


class AgentChatResponse(BaseModel):
    """Response from agent mode chat"""

    status: str  # success, failed, max_iterations
    final_answer: Optional[str] = None
    steps: List[AgentStepInfo] = Field(default_factory=list)
    total_iterations: int = 0
    model_used: Optional[str] = None
    error: Optional[str] = None


@router.post("/assistant/agent-chat", response_model=AgentChatResponse)
async def agent_mode_chat(request: AgentChatRequest) -> AgentChatResponse:
    """
    Agent mode chat using LangChain's native tool calling.

    Unlike regular chat, this endpoint can:
    - Execute multiple steps to complete a task
    - Analyze errors and retry with different approaches
    - Use tools to check/install CLI, configure agents, etc.
    """
    try:
        from backend.app.services.runtime.agent_executor import (
            LangChainAgentExecutor,
            AgentStatus,
            LANGCHAIN_AGENTS_AVAILABLE,
        )
        from .config_assistant_tools import get_config_assistant_tools

        if not LANGCHAIN_AGENTS_AVAILABLE:
            return AgentChatResponse(
                status="failed",
                error="LangChain agents not available. Please install langchain-google-vertexai.",
                total_iterations=0,
            )

        # Check available providers
        available_providers = get_available_providers()
        if not any(available_providers.values()):
            return AgentChatResponse(
                status="failed",
                error="No LLM configured. Please set up an API key first.",
                total_iterations=0,
            )

        # Select best available model
        selection = select_best_model(available_providers)
        if not selection:
            return AgentChatResponse(
                status="failed",
                error="No suitable LLM model available.",
                total_iterations=0,
            )

        provider, model = selection
        logger.info(f"Agent mode using LangChain with: {provider}/{model}")

        # Get agent tools
        tools = get_config_assistant_tools()

        # Get LLM manager and extract credentials for LangChain
        llm_manager = create_llm_provider_manager()
        llm_provider = llm_manager.get_provider(provider)

        # Extract credentials based on provider type
        api_key = None
        project_id = None
        location = "us-central1"

        if llm_provider:
            api_key = getattr(llm_provider, "api_key", None)
            if provider == "vertex-ai":
                project_id = getattr(llm_provider, "project_id", None)
                location = getattr(llm_provider, "location", None) or "us-central1"

        # Create LangChain agent executor with credentials from Mindscape config
        executor = LangChainAgentExecutor(
            provider=provider,
            model=model,
            tools=tools,
            max_iterations=request.max_iterations,
            api_key=api_key,
            project_id=project_id,
            location=location,
        )

        # Build context dict
        context_dict = None
        if request.context:
            context_dict = {
                "current_tab": request.context.current_tab,
                "current_section": request.context.current_section,
                "governance": request.context.governance,
            }

        # Run agent
        result = await executor.run(request.message, context=context_dict)

        # Convert result to response
        steps_info = [
            AgentStepInfo(
                step_number=step.step_number,
                thought=step.thought,
                action=step.action,
                action_result=step.observation[:200] if step.observation else None,
                success=step.success,
            )
            for step in result.steps
        ]

        return AgentChatResponse(
            status=result.status.value,
            final_answer=result.final_answer,
            steps=steps_info,
            total_iterations=result.total_iterations,
            model_used=f"{provider}/{model}",
            error=result.error,
        )

    except Exception as e:
        logger.error(f"Error in agent mode chat: {e}", exc_info=True)
        return AgentChatResponse(
            status="failed",
            error=str(e),
            total_iterations=0,
        )

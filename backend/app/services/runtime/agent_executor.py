"""
LangChain-based Agent Executor for Mindscape

Uses LangChain's battle-tested AgentExecutor with native tool calling,
instead of fragile JSON parsing from text responses.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status"""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    MAX_ITERATIONS = "max_iterations"
    CANCELLED = "cancelled"


@dataclass
class AgentStep:
    """Single step in agent execution"""

    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    success: bool = True


@dataclass
class AgentResult:
    """Final result of agent execution"""

    status: AgentStatus
    final_answer: Optional[str] = None
    steps: List[AgentStep] = field(default_factory=list)
    total_iterations: int = 0
    total_duration_ms: int = 0
    error: Optional[str] = None


# Check for LangChain availability
try:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.tools import StructuredTool
    from langchain_google_vertexai import ChatVertexAI
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic

    LANGCHAIN_AGENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"LangChain agents not available: {e}")
    LANGCHAIN_AGENTS_AVAILABLE = False


def create_langchain_tools(tools: Dict[str, Callable]) -> List:
    """Convert callable functions to LangChain StructuredTool.

    Properly handles async functions by using the coroutine parameter.
    """
    if not LANGCHAIN_AGENTS_AVAILABLE:
        raise ImportError("LangChain is required for agent execution")

    import asyncio

    lc_tools = []
    for name, func in tools.items():
        # Check if function is async
        if asyncio.iscoroutinefunction(func):
            tool = StructuredTool.from_function(
                coroutine=func,  # Use coroutine for async functions
                name=name,
                description=func.__doc__ or f"Tool: {name}",
            )
        else:
            tool = StructuredTool.from_function(
                func=func,
                name=name,
                description=func.__doc__ or f"Tool: {name}",
            )
        lc_tools.append(tool)

    return lc_tools


def get_langchain_llm(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    location: str = "us-central1",
):
    """
    Get LangChain LLM based on provider with Mindscape credentials.

    Args:
        provider: LLM provider name (vertex-ai, openai, anthropic)
        model: Model name
        api_key: API key or service account JSON for the provider
        project_id: GCP project ID (for Vertex AI)
        location: GCP location (for Vertex AI)
    """
    if not LANGCHAIN_AGENTS_AVAILABLE:
        raise ImportError("LangChain is required")

    if provider == "vertex-ai":
        # For Vertex AI, we need project and credentials
        kwargs = {"model": model, "temperature": 0.3, "location": location}

        if project_id:
            kwargs["project"] = project_id

        if api_key:
            # If api_key is a service account JSON string, parse it
            try:
                import json
                from google.oauth2 import service_account

                sa_info = json.loads(api_key)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info
                )
                kwargs["credentials"] = credentials

                # Extract project_id from service account if not provided
                if not project_id and "project_id" in sa_info:
                    kwargs["project"] = sa_info["project_id"]
            except (json.JSONDecodeError, ValueError):
                # api_key might be a file path, skip credentials setup
                pass

        return ChatVertexAI(**kwargs)

    elif provider == "openai":
        kwargs = {"model": model, "temperature": 0.3}
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(**kwargs)

    elif provider == "anthropic":
        kwargs = {"model": model, "temperature": 0.3}
        if api_key:
            kwargs["api_key"] = api_key
        return ChatAnthropic(**kwargs)

    else:
        raise ValueError(f"Unsupported provider: {provider}")


class LangChainAgentExecutor:
    """
    Agent Executor using LangChain's native tool calling.

    This uses proper function calling APIs instead of parsing JSON from text.

    Usage:
        executor = LangChainAgentExecutor(
            provider="vertex-ai",
            model="gemini-2.5-pro",
            tools={"check_cli": check_cli_func}
        )
        result = await executor.run("Install moltbot CLI")
    """

    AGENT_PROMPT = (
        ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an intelligent agent that helps configure Mindscape AI.

You have access to tools for:
- Checking and installing agent CLIs
- Enabling and configuring agents
- Managing agent settings

Be helpful, concise, and action-oriented. When a task requires installation,
first check if the CLI is available, then install if needed.

Always verify your actions completed successfully.""",
                ),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        if LANGCHAIN_AGENTS_AVAILABLE
        else None
    )

    def __init__(
        self,
        provider: str,
        model: str,
        tools: Dict[str, Callable],
        max_iterations: int = 10,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        location: str = "us-central1",
    ):
        """
        Initialize LangChain Agent Executor.

        Args:
            provider: LLM provider (vertex-ai, openai, anthropic)
            model: Model name
            tools: Dict of tool_name -> async callable
            max_iterations: Maximum number of agent steps
            api_key: API key or service account JSON
            project_id: GCP project ID (for Vertex AI)
            location: GCP location (for Vertex AI)
        """
        if not LANGCHAIN_AGENTS_AVAILABLE:
            raise ImportError(
                "LangChain agents not available. Install with: "
                "pip install langchain langchain-google-vertexai"
            )

        self.provider = provider
        self.model = model
        self.max_iterations = max_iterations

        # Create LangChain LLM with credentials
        self.llm = get_langchain_llm(
            provider, model, api_key=api_key, project_id=project_id, location=location
        )

        # Convert tools to LangChain format
        self.lc_tools = create_langchain_tools(tools)

        # Create agent
        self.agent = create_tool_calling_agent(
            llm=self.llm,
            tools=self.lc_tools,
            prompt=self.AGENT_PROMPT,
        )

        # Create executor
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.lc_tools,
            verbose=True,
            max_iterations=max_iterations,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
        )

    async def run(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Execute task with LangChain agent loop.

        Args:
            task: Task description
            context: Optional context information

        Returns:
            AgentResult with execution details
        """
        start_time = datetime.utcnow()

        try:
            # Add context to input if provided
            input_text = task
            if context:
                input_text = f"Context: {context}\n\nTask: {task}"

            # Execute agent
            result = await self.executor.ainvoke(
                {
                    "input": input_text,
                    "chat_history": [],
                }
            )

            # Parse intermediate steps
            steps = []
            intermediate_steps = result.get("intermediate_steps", [])
            for i, (action, observation) in enumerate(intermediate_steps):
                steps.append(
                    AgentStep(
                        step_number=i + 1,
                        thought=getattr(action, "log", ""),
                        action=action.tool if hasattr(action, "tool") else str(action),
                        action_input=(
                            action.tool_input if hasattr(action, "tool_input") else {}
                        ),
                        observation=str(observation)[:500],
                        success=True,
                    )
                )

            return AgentResult(
                status=AgentStatus.SUCCESS,
                final_answer=result.get("output", ""),
                steps=steps,
                total_iterations=len(steps),
                total_duration_ms=int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                ),
            )

        except Exception as e:
            logger.exception("Agent execution failed")
            return AgentResult(
                status=AgentStatus.FAILED,
                error=str(e),
                total_duration_ms=int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                ),
            )


# Convenience function
def create_agent_executor(
    provider: str,
    model: str,
    tools: Dict[str, Callable],
    max_iterations: int = 10,
) -> LangChainAgentExecutor:
    """Create a LangChain-based agent executor"""
    return LangChainAgentExecutor(
        provider=provider,
        model=model,
        tools=tools,
        max_iterations=max_iterations,
    )


# Keep backward compatibility - export same interface
MindscapeAgentExecutor = LangChainAgentExecutor

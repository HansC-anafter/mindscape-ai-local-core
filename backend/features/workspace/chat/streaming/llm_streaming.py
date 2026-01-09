"""
LLM streaming response handling for different providers
"""

import logging
import json
import uuid
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.services.conversation.response_parser import parse_agent_mode_response
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore

from ..playbook.trigger import check_and_trigger_playbook
from ..playbook.executor import execute_playbook_for_hybrid_mode

logger = logging.getLogger(__name__)


async def stream_openai_response(
    provider: Any,
    messages: List[Dict[str, Any]],
    model_name: str,
    openai_key: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Stream response from OpenAI provider

    Args:
        provider: OpenAI provider instance
        messages: Messages list
        model_name: Model name
        openai_key: Optional OpenAI API key for fallback

    Yields:
        SSE event strings with chunk content
    """
    use_provider_stream = hasattr(provider, 'chat_completion_stream')

    if not use_provider_stream:
        # Fallback to direct client
        logger.warning("Provider does not support chat_completion_stream, using direct client")
        import openai
        openai_key_for_streaming = provider.api_key if hasattr(provider, 'api_key') else openai_key
        client = openai.AsyncOpenAI(api_key=openai_key_for_streaming)

    full_text = ""

    if use_provider_stream:
        # Use improved provider abstraction
        async for chunk_content in provider.chat_completion_stream(
            messages=messages,
            model=model_name,
            temperature=0.7,
            max_tokens=8000
        ):
            full_text += chunk_content
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_content})}\n\n"
    else:
        # Fallback: direct client usage
        request_params = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
            "stream": True
        }

        # Handle max_completion_tokens for newer models
        model_lower = model_name.lower()
        is_newer_model = "gpt-5" in model_lower or "o1" in model_lower or "o3" in model_lower
        if is_newer_model:
            request_params["extra_body"] = {"max_completion_tokens": 8000}
        else:
            request_params["max_tokens"] = 8000

        # Create streaming request
        stream = await client.chat.completions.create(**request_params)
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    full_text += delta.content
                    yield f"data: {json.dumps({'type': 'chunk', 'content': delta.content})}\n\n"


async def stream_vertexai_response(
    provider: Any,
    messages: List[Dict[str, Any]],
    model_name: str
) -> AsyncGenerator[str, None]:
    """
    Stream response from VertexAI provider

    Args:
        provider: VertexAI provider instance
        messages: Messages list
        model_name: Model name

    Yields:
        SSE event strings with chunk content
    """
    logger.info(f"Using VertexAIProvider for model {model_name}")
    full_text = ""

    # Use provider's chat_completion_stream if available
    if hasattr(provider, 'chat_completion_stream'):
        async for chunk_content in provider.chat_completion_stream(
            messages=messages,
            model=model_name,
            temperature=0.7,
            max_tokens=8000
        ):
            full_text += chunk_content
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_content})}\n\n"
    else:
        # Fallback: use non-streaming and simulate streaming
        logger.warning("VertexAIProvider does not support streaming, using non-streaming mode")
        response_text = await provider.chat_completion(
            messages=messages,
            model=model_name,
            temperature=0.7,
            max_tokens=8000
        )
        # Simulate streaming by sending chunks
        chunk_size = 10
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i+chunk_size]
            full_text += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"


def create_assistant_event(
    full_text: str,
    user_event_id: str,
    profile_id: str,
    project_id: str,
    workspace_id: str,
    thread_id: Optional[str],
    store: MindscapeStore
) -> MindEvent:
    """
    Create assistant event from response text

    Args:
        full_text: Full response text
        user_event_id: User event ID this responds to
        profile_id: Profile ID
        project_id: Project ID
        workspace_id: Workspace ID
        thread_id: Thread ID (optional)
        store: MindscapeStore instance

    Returns:
        Created MindEvent
    """
    assistant_event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        actor=EventActor.ASSISTANT,
        channel="local_workspace",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        event_type=EventType.MESSAGE,
        payload={"message": full_text, "response_to": user_event_id},
        entity_ids=[],
        metadata={}
    )
    store.create_event(assistant_event)
    logger.info(f"[LLMStreaming] Created assistant event {assistant_event.id}, message length: {len(full_text)} chars, thread_id={thread_id}")
    
    # Update thread statistics
    if thread_id:
        try:
            from datetime import datetime
            thread = store.conversation_threads.get_thread(thread_id)
            if thread:
                # Use COUNT query to accurately calculate message count (not dependent on limit)
                message_count = store.events.count_messages_by_thread(
                    workspace_id=workspace_id,
                    thread_id=thread_id
                )
                
                store.conversation_threads.update_thread(
                    thread_id=thread_id,
                    last_message_at=datetime.utcnow(),
                    message_count=message_count
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to update thread statistics: {e}")
    
    return assistant_event


async def handle_hybrid_mode_response(
    full_text: str,
    message: str,
    workspace_id: str,
    profile_id: str,
    profile: Optional[Any],
    store: MindscapeStore
) -> AsyncGenerator[str, None]:
    """
    Handle hybrid mode response parsing and playbook execution

    Args:
        full_text: Full LLM response text
        message: Original user message
        workspace_id: Workspace ID
        profile_id: Profile ID
        profile: Profile object (optional)
        store: MindscapeStore instance

    Yields:
        SSE event strings
    """
    # Parse two-part response
    parsed_response = parse_agent_mode_response(full_text)
    logger.info(
        f"[AgentMode] Parsed response - Part1 length: {len(parsed_response['part1'])}, "
        f"Part2 length: {len(parsed_response['part2'])}, "
        f"Tasks: {len(parsed_response['executable_tasks'])}"
    )

    # Send parsed response structure via SSE
    yield f"data: {json.dumps({'type': 'agent_mode_parsed', 'part1': parsed_response['part1'], 'part2': parsed_response['part2'], 'executable_tasks': parsed_response['executable_tasks']})}\n\n"

    # Analyze executable tasks and select playbook
    if parsed_response['executable_tasks']:
        try:
            execution_result = await execute_playbook_for_hybrid_mode(
                message=message,
                executable_tasks=parsed_response['executable_tasks'],
                workspace_id=workspace_id,
                profile_id=profile_id,
                profile=profile,
                store=store
            )

            if execution_result:
                # Send execution result
                yield f"data: {json.dumps({'type': 'agent_mode_playbook_executed', 'playbook_code': execution_result['playbook_code'], 'execution_id': execution_result['execution_id'], 'tasks': execution_result['tasks']})}\n\n"
                logger.info(
                    f"[AgentMode] Playbook {execution_result['playbook_code']} executed successfully, "
                    f"execution_id={execution_result['execution_id']}"
                )
            else:
                logger.info(f"[AgentMode] No playbook selected for executable tasks")
        except Exception as e:
            logger.warning(f"[AgentMode] Failed to analyze intent or execute playbook: {e}", exc_info=True)


async def handle_execution_mode_playbook_trigger(
    full_text: str,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    execution_mode: str,
    execution_playbook_result: Optional[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Handle execution mode playbook trigger check (fallback mechanism)

    Args:
        full_text: Full LLM response text
        workspace: Workspace object
        workspace_id: Workspace ID
        profile_id: Profile ID
        execution_mode: Execution mode
        execution_playbook_result: Optional direct execution result

    Yields:
        SSE event strings
    """
    # If direct playbook execution succeeded, send result
    if execution_playbook_result:
        logger.info(f"[ExecutionMode] Direct playbook execution succeeded, sending result via SSE")
        yield f"data: {json.dumps({'type': 'execution_mode_playbook_executed', **execution_playbook_result})}\n\n"
        # Generate summary response (optional)
        summary_text = f"I've started executing the playbook '{execution_playbook_result.get('playbook_code', 'unknown')}'. Check the execution panel for progress."
        yield f"data: {json.dumps({'type': 'chunk', 'content': summary_text})}\n\n"
    else:
        # Check for playbook trigger (fallback: LLM-generated marker)
        # Note: This is a fallback mechanism. Primary path is direct playbook.run (P2)
        if execution_mode == "execution":
            logger.info(
                f"[PlaybookTrigger] Checking trigger after response (fallback). "
                f"execution_mode={execution_mode}, workspace_id={workspace_id}"
            )
            playbook_trigger_result = await check_and_trigger_playbook(
                full_text=full_text,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                execution_mode=execution_mode
            )
            if playbook_trigger_result:
                logger.info(f"[PlaybookTrigger] Trigger result: {playbook_trigger_result}")
                yield f"data: {json.dumps({'type': 'playbook_triggered', **playbook_trigger_result})}\n\n"
            else:
                logger.info(f"[PlaybookTrigger] No trigger result returned")


async def stream_llm_response(
    provider: Any,
    provider_type: str,
    messages: List[Dict[str, Any]],
    model_name: str,
    execution_mode: str,
    user_event_id: str,
    profile_id: str,
    project_id: str,
    workspace_id: str,
    thread_id: Optional[str],
    workspace: Workspace,
    message: str,
    profile: Optional[Any],
    store: MindscapeStore,
    context_token_count: int,
    execution_playbook_result: Optional[Dict[str, Any]] = None,
    openai_key: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Stream LLM response based on provider type and handle post-processing

    Args:
        provider: LLM provider instance
        provider_type: Provider type name
        messages: Messages list
        model_name: Model name
        execution_mode: Execution mode
        full_text: Accumulated full text (will be updated)
        user_event_id: User event ID
        profile_id: Profile ID
        project_id: Project ID
        workspace_id: Workspace ID
        workspace: Workspace object
        message: Original user message
        profile: Profile object (optional)
        store: MindscapeStore instance
        context_token_count: Context token count
        execution_playbook_result: Optional direct execution result
        openai_key: Optional OpenAI key for fallback

    Yields:
        SSE event strings
    """
    full_text = ""

    if provider_type == 'OpenAIProvider':
        # Stream OpenAI response
        async for event in stream_openai_response(provider, messages, model_name, openai_key):
            yield event
            # Extract chunk content to accumulate full_text
            if event.startswith("data: "):
                try:
                    data = json.loads(event[6:].strip())
                    if data.get('type') == 'chunk':
                        full_text += data.get('content', '')
                except:
                    pass

        # Create assistant event
        assistant_event = create_assistant_event(
            full_text, user_event_id, profile_id, project_id, workspace_id, thread_id, store
        )

        # Handle hybrid mode
        if execution_mode == "hybrid":
            async for event in handle_hybrid_mode_response(
                full_text, message, workspace_id, profile_id, profile, store
            ):
                yield event

        # Handle execution mode playbook trigger
        async for event in handle_execution_mode_playbook_trigger(
            full_text, workspace, workspace_id, profile_id, execution_mode, execution_playbook_result
        ):
            yield event

        # Send final completion event (main response is complete)
        yield f"data: {json.dumps({'type': 'complete', 'event_id': assistant_event.id, 'context_tokens': context_token_count, 'is_final': True})}\n\n"
        logger.info(f"[LLMStreaming] Sent final complete event (OpenAI), full_text length: {len(full_text)} chars")

    elif provider_type == 'AnthropicProvider':
        # Anthropic streaming support (if needed in future)
        logger.warning(f"AnthropicProvider streaming not yet implemented for SSE")
        yield f"data: {json.dumps({'type': 'error', 'message': 'Streaming not supported for Anthropic provider yet'})}\n\n"

    elif provider_type == 'VertexAIProvider':
        # Stream VertexAI response
        async for event in stream_vertexai_response(provider, messages, model_name):
            yield event
            # Extract chunk content to accumulate full_text
            if event.startswith("data: "):
                try:
                    data = json.loads(event[6:].strip())
                    if data.get('type') == 'chunk':
                        full_text += data.get('content', '')
                except:
                    pass

        # Create assistant event
        assistant_event = create_assistant_event(
            full_text, user_event_id, profile_id, project_id, workspace_id, thread_id, store
        )

        # Handle hybrid mode
        if execution_mode == "hybrid":
            async for event in handle_hybrid_mode_response(
                full_text, message, workspace_id, profile_id, profile, store
            ):
                yield event

        # Handle execution mode playbook trigger
        async for event in handle_execution_mode_playbook_trigger(
            full_text, workspace, workspace_id, profile_id, execution_mode, execution_playbook_result
        ):
            yield event

        # Send final completion event (main response is complete)
        yield f"data: {json.dumps({'type': 'complete', 'event_id': assistant_event.id, 'context_tokens': context_token_count, 'is_final': True})}\n\n"
        logger.info(f"[LLMStreaming] Sent final complete event (VertexAI), full_text length: {len(full_text)} chars")

    else:
        # Other providers - not yet supported
        logger.warning(f"Provider {provider_type} streaming not yet implemented for SSE")
        yield f"data: {json.dumps({'type': 'error', 'message': f'Streaming not supported for {provider_type}'})}\n\n"


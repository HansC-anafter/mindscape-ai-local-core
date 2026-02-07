'use client';

/**
 * useMessageStream - Real-time SSE stream for chat messages
 *
 * Subscribes to SSE `/events/stream?event_types=message` for incremental updates.
 * Used alongside useChatEvents for initial load + real-time updates pattern.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ChatMessage } from './useChatEvents';
import { subscribeEventStream, UnifiedEvent } from '@/components/workspace/eventProjector';

export interface UseMessageStreamOptions {
    threadId?: string | null;
    enabled?: boolean;
}

/**
 * Transform SSE event to ChatMessage format
 */
function eventToMessage(event: UnifiedEvent): ChatMessage | null {
    // Only handle message events
    if (event.type !== 'message') {
        return null;
    }

    // Cast payload to any for message event fields (different from typed UnifiedEvent payload)
    const payload = (event.payload || {}) as any;
    const metadata = (event as any).metadata || {};

    // Determine role from actor
    let role: 'user' | 'assistant' | 'system' = 'assistant';
    if (event.actor === 'user') {
        role = 'user';
    } else if (event.actor === 'system') {
        role = 'system';
    }

    // Extract content from payload
    const content = payload.text || payload.content || payload.message || '';
    if (!content) {
        return null;
    }

    return {
        id: event.id,
        role,
        content,
        timestamp: new Date(event.timestamp),
        event_type: event.type,
        is_welcome: payload.is_welcome,
        suggestions: payload.suggestions,
        triggered_playbook: payload.triggered_playbook,
        agentMode: payload.agent_mode,
        project_assignment: payload.project_assignment,
    };
}

export function useMessageStream(
    workspaceId: string,
    apiUrl: string = '',
    options?: UseMessageStreamOptions
) {
    const { threadId, enabled = true } = options || {};

    const [streamedMessages, setStreamedMessages] = useState<ChatMessage[]>([]);
    const [connected, setConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Track seen message IDs to avoid duplicates
    const seenIdsRef = useRef<Set<string>>(new Set());

    // Clear state when thread changes
    useEffect(() => {
        setStreamedMessages([]);
        seenIdsRef.current.clear();
    }, [threadId]);

    useEffect(() => {
        if (!workspaceId || !enabled) {
            return;
        }

        console.log('[useMessageStream] Connecting to SSE for message events');
        setConnected(false);
        setError(null);

        const unsubscribe = subscribeEventStream(workspaceId, {
            apiUrl,
            eventTypes: ['message', 'pipeline_stage', 'execution_plan', 'run_started', 'run_completed', 'run_failed', 'step_start', 'step_progress', 'step_complete', 'step_error'],  // Subscribe to message and execution events
            onEvent: (event) => {
                // Forward execution-related events to useExecutionState via CustomEvent
                if (event.type !== 'message') {
                    const payload = event.payload as any;
                    window.dispatchEvent(new CustomEvent('execution-event', {
                        detail: {
                            type: event.type,
                            run_id: payload?.run_id || (event as any).metadata?.run_id,
                            stage: payload?.stage,
                            message: payload?.message || payload?.text,
                            metadata: (event as any).metadata,
                            plan: payload?.plan,
                            stepId: payload?.step_id,
                            error: payload?.error,
                        }
                    }));
                    console.log(`[useMessageStream] Forwarded ${event.type} event to execution state`);
                    return;
                }

                // Filter by thread if specified
                const eventPayload = event.payload as any;
                const eventThreadId = (event as any).metadata?.thread_id || eventPayload?.thread_id;
                if (threadId && eventThreadId && eventThreadId !== threadId) {
                    return;
                }

                // Skip if already seen
                if (seenIdsRef.current.has(event.id)) {
                    return;
                }

                // Transform and add message
                const message = eventToMessage(event);
                if (message) {
                    console.log('[useMessageStream] Received new message via SSE:', message.id);
                    seenIdsRef.current.add(event.id);
                    setStreamedMessages(prev => [...prev, message]);
                }

                // Mark as connected on first event
                setConnected(true);
            },
            onError: (err) => {
                console.error('[useMessageStream] SSE error:', err);
                setError(err.message);
                setConnected(false);
            },
        });

        // Mark as potentially connected (SSE opened)
        setConnected(true);

        return () => {
            console.log('[useMessageStream] Disconnecting SSE');
            unsubscribe();
            setConnected(false);
        };
    }, [workspaceId, apiUrl, threadId, enabled]);

    /**
     * Mark a message ID as seen (used when merging with initial load)
     */
    const markAsSeen = useCallback((messageId: string) => {
        seenIdsRef.current.add(messageId);
    }, []);

    /**
     * Mark multiple message IDs as seen
     */
    const markManyAsSeen = useCallback((messageIds: string[]) => {
        messageIds.forEach(id => seenIdsRef.current.add(id));
    }, []);

    /**
     * Clear streamed messages (useful when doing a full reload)
     */
    const clearStreamedMessages = useCallback(() => {
        setStreamedMessages([]);
    }, []);

    return {
        streamedMessages,
        connected,
        error,
        markAsSeen,
        markManyAsSeen,
        clearStreamedMessages,
    };
}

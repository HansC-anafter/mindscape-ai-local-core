'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

export interface ProjectAssignment {
  project_id?: string;
  phase_id?: string;
  project_title?: string;
  relation: string;
  confidence: number;
  reasoning?: string;
  requires_ui_confirmation: boolean;
  candidates?: Array<{
    project_id?: string;
    project?: any;
    similarity?: number;
  }>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  event_type?: string;
  is_welcome?: boolean;
  suggestions?: string[];
  triggered_playbook?: {
    playbook_code: string;
    execution_id?: string;
    status: string;
    message?: string;
  };
  // Agent Mode support: Two-part response structure
  agentMode?: {
    part1: string;  // Understanding & Response
    part2: string;  // Executable Next Steps
    executable_tasks: string[];  // Extracted task list
  };
  // Project Assignment support
  project_assignment?: ProjectAssignment;
}

export interface UseChatEventsOptions {
  threadId?: string | null;
  projectId?: string | null;
  enabled?: boolean;
}

export function useChatEvents(
  workspaceId: string,
  apiUrl: string = '',
  options?: UseChatEventsOptions
) {
  const { threadId, projectId, enabled = true } = options || {};

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quickStartSuggestions, setQuickStartSuggestions] = useState<string[]>([]);
  const [fileAnalysisResult, setFileAnalysisResult] = useState<any>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [autoLoadAttempted, setAutoLoadAttempted] = useState(false);

  // AbortController for canceling requests on thread switch
  const abortControllerRef = useRef<AbortController | null>(null);

  const loadEvents = useCallback(async (beforeId?: string, append: boolean = false) => {
    if (!enabled) {
      return;
    }

    // Prevent duplicate requests
    if (!append && loading) {
      return;
    }

    // Abort previous request if exists
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Create new AbortController for this request
    abortControllerRef.current = new AbortController();

    try {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      setError(null);

      const url = new URL(`${apiUrl}/api/v1/workspaces/${workspaceId}/events`);
      // Increase limit to load more messages initially (was 25, now 200 to match backend max)
      url.searchParams.set('limit', beforeId ? '100' : '200');
      if (beforeId) {
        url.searchParams.set('before_id', beforeId);
      }
      // 🆕 添加 thread_id 過濾（如果提供）
      // 注意：如果 threadId 為 null/undefined，後端會返回所有事件（向後兼容）
      // 但實際上後端會自動使用 default thread，所以這裡可以選擇性地傳遞
      if (threadId) {
        url.searchParams.set('thread_id', threadId);
      }

      const eventsResponse = await fetch(url.toString(), {
        signal: abortControllerRef.current.signal
      });

      if (!eventsResponse.ok) {
        const errorText = await eventsResponse.text().catch(() => 'Unknown error');
        console.error(`[useChatEvents] Failed to load events: ${eventsResponse.status}`, errorText);
        throw new Error(`Failed to load events: ${eventsResponse.status} - ${errorText.substring(0, 100)}`);
      }

      const eventsData = await eventsResponse.json();
      console.log(`[useChatEvents] Loaded ${eventsData.events?.length || 0} events for workspace ${workspaceId}`);

      // Store original events for metadata access
      const eventsMap = new Map();
      (eventsData.events || []).forEach((e: any) => {
        eventsMap.set(e.id, e);
      });

      const allEvents = eventsData.events || [];
      console.log(`[useChatEvents] Total events: ${allEvents.length}, event types:`,
        [...new Set(allEvents.map((e: any) => e.event_type))]);

      const chatMessages: ChatMessage[] = allEvents
        .slice()
        .reverse()
        .filter((e: any) =>
          e.event_type === 'message' ||
          e.event_type === 'playbook_step' ||
          e.event_type === 'tool_call'
        )
        .map((e: any) => ({
          id: e.id,
          role: e.actor === 'user' ? 'user' : 'assistant',
          content: e.payload?.message || e.payload?.text ||
                   (e.event_type === 'playbook_step' ? `Playbook step: ${e.payload?.step || ''}` : '') ||
                   (e.event_type === 'tool_call' ? `Tool: ${e.payload?.tool_fqn || ''}` : ''),
          timestamp: new Date(e.timestamp),
          event_type: e.event_type,
          is_welcome: e.payload?.is_welcome === true,
          suggestions: e.payload?.suggestions || [],
          triggered_playbook: e.payload?.playbook_code ? {
            playbook_code: e.payload.playbook_code,
            execution_id: e.payload.execution_id,
            status: e.payload.status || 'triggered',
            message: e.payload.message
          } : undefined,
          project_assignment: e.metadata?.project_assignment || undefined,
          _originalEvent: e  // Store original event for metadata access
        }));

      console.log(`[useChatEvents] Filtered to ${chatMessages.length} chat messages`);

      if (append) {
        setMessages(prev => [...chatMessages, ...prev]);
      } else {
        setMessages(chatMessages);
        setAutoLoadAttempted(false); // Reset auto-load flag on initial load
      }

      setHasMore(eventsData.has_more === true);

      // Only show quick start suggestions if:
      // 1. There's a welcome message with suggestions
      // 2. There are NO user messages yet (truly cold start - user hasn't interacted)
      const welcomeMessage = chatMessages.find(m => m.is_welcome && m.suggestions && m.suggestions.length > 0);
      const hasUserMessages = chatMessages.some(m => m.role === 'user');

      if (welcomeMessage && welcomeMessage.suggestions && !hasUserMessages) {
        // Check if this is a cold start by looking at the original event metadata
        const originalEvent = (welcomeMessage as any)._originalEvent;
        const isColdStart = originalEvent?.metadata?.is_cold_start === true;

        // Only show if it's a cold start and no user messages yet
        if (isColdStart && !hasUserMessages) {
          // Filter out placeholder / malformed suggestions (e.g. "或許可以開始")
          const cleaned = (welcomeMessage.suggestions || [])
            .map((s: string) => (s || '').trim())
            .filter((s: string) => s.length > 0)
            .filter((s: string) => !/^或許(也)?可以開始/i.test(s) && !/^maybe\s*(we)?\s*can\s*start/i.test(s));
          setQuickStartSuggestions(cleaned);
        } else {
          setQuickStartSuggestions([]);
        }
      } else {
        // Clear suggestions if there are user messages or no welcome message
        setQuickStartSuggestions([]);
      }

      for (const event of eventsData.events || []) {
        if (event.event_type === 'message' &&
            event.actor === 'user' &&
            event.payload?.files &&
            event.payload.files.length > 0 &&
            event.metadata?.file_analysis) {
          const analysisResult = event.metadata.file_analysis;
          if (analysisResult && analysisResult.collaboration_results) {
            setFileAnalysisResult(analysisResult);
            break;
          }
        }
      }
    } catch (err: any) {
      // Handle AbortError gracefully (thread switch)
      if (err.name === 'AbortError') {
        console.log('[useChatEvents] Request aborted due to thread switch');
        return;
      }
      console.error('Failed to load chat history:', err);
      setError(err.message || 'Failed to load chat history');
    } finally {
      setLoading(false);
      setLoadingMore(false);
      abortControllerRef.current = null;
    }
  }, [workspaceId, apiUrl, threadId, enabled, loading]);

  // Load events when threadId or enabled changes
  // Note: If threadId is null/undefined, backend will use default thread
  useEffect(() => {
    if (enabled && threadId !== undefined) {
      loadEvents();
    }
  }, [threadId, enabled, loadEvents]);

  // Cleanup: abort ongoing requests when component unmounts or threadId changes
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, [threadId]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || messages.length === 0) return;

    const oldestMessage = messages[0];
    await loadEvents(oldestMessage.id, true);
  }, [messages, hasMore, loadingMore, loadEvents]);

  // Auto-load more messages once after initial load if hasMore is true
  useEffect(() => {
    if (hasMore && !loading && !loadingMore && messages.length > 0 && !autoLoadAttempted) {
      setAutoLoadAttempted(true);
      const timer = setTimeout(() => {
        loadMore();
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [hasMore, loading, loadingMore, messages.length, autoLoadAttempted, loadMore]);

  return {
    messages,
    loading,
    error,
    quickStartSuggestions,
    fileAnalysisResult,
    reload: loadEvents,
    setMessages,
    setFileAnalysisResult,
    hasMore,
    loadingMore,
    loadMore
  };
}



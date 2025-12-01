'use client';

import { useState, useEffect, useCallback } from 'react';

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
}

export function useChatEvents(workspaceId: string, apiUrl: string = '') {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quickStartSuggestions, setQuickStartSuggestions] = useState<string[]>([]);
  const [fileAnalysisResult, setFileAnalysisResult] = useState<any>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadEvents = useCallback(async (beforeId?: string, append: boolean = false) => {
    try {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      setError(null);

      const url = new URL(`${apiUrl}/api/v1/workspaces/${workspaceId}/events`);
      url.searchParams.set('limit', '25');
      if (beforeId) {
        url.searchParams.set('before_id', beforeId);
      }

      const eventsResponse = await fetch(url.toString());

      if (!eventsResponse.ok) {
        throw new Error(`Failed to load events: ${eventsResponse.status}`);
      }

      const eventsData = await eventsResponse.json();

      const chatMessages: ChatMessage[] = (eventsData.events || [])
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
          } : undefined
        }));

      if (append) {
        setMessages(prev => [...chatMessages, ...prev]);
      } else {
        setMessages(chatMessages);
      }

      setHasMore(eventsData.has_more === true);

      const welcomeMessage = chatMessages.find(m => m.is_welcome && m.suggestions && m.suggestions.length > 0);
      if (welcomeMessage && welcomeMessage.suggestions) {
        setQuickStartSuggestions(welcomeMessage.suggestions);
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
      console.error('Failed to load chat history:', err);
      setError(err.message || 'Failed to load chat history');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [workspaceId, apiUrl]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore || messages.length === 0) return;

    const oldestMessage = messages[0];
    await loadEvents(oldestMessage.id, true);
  }, [messages, hasMore, loadingMore, loadEvents]);

  useEffect(() => {
    loadEvents();

    // Note: workspace-chat-updated event handling is now managed by WorkspaceChat component
    // to prevent unwanted scroll resets when user is scrolling
  }, [loadEvents]);

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



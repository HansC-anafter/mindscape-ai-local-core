'use client';

import { useCallback, useEffect } from 'react';
import { useWorkspaceMetadata } from '@/contexts/WorkspaceMetadataContext';
import { useMessages } from '@/contexts/MessagesContext';

interface UseWorkspaceDataOptions {
  enabled?: boolean;
  onWorkspaceLoaded?: (data: any) => void;
  onSystemHealthLoaded?: (health: any) => void;
  onTokenCountLoaded?: (count: number | null) => void;
}

/**
 * useWorkspaceData Hook
 * Manages workspace information, system health, and token count loading.
 *
 * @param workspaceId The workspace ID.
 * @param apiUrl The base API URL.
 * @param options Optional configuration options.
 * @returns An object containing loading functions and state.
 */
export function useWorkspaceData(
  workspaceId: string,
  apiUrl: string = '',
  options?: UseWorkspaceDataOptions
) {
  const {
    workspaceTitle,
    setWorkspaceTitle,
    systemHealth,
    setSystemHealth,
    contextTokenCount,
    setContextTokenCount,
    setPreferredAgent,
  } = useWorkspaceMetadata();

  const { messagesLoading } = useMessages();

  const {
    enabled = true,
    onWorkspaceLoaded,
    onSystemHealthLoaded,
    onTokenCountLoaded,
  } = options || {};

  const loadWorkspaceInfo = useCallback(async () => {
    if (!enabled || !workspaceId || !apiUrl) {
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        setWorkspaceTitle(data.title || data.name || '');
        // Load preferred_agent if exists
        if (data.preferred_agent !== undefined) {
          setPreferredAgent(data.preferred_agent);
        }
        onWorkspaceLoaded?.(data);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError') {
        console.error('Failed to load workspace info:', err);
      }
    }
  }, [workspaceId, apiUrl, enabled, setWorkspaceTitle, setPreferredAgent, onWorkspaceLoaded]);

  const loadSystemHealth = useCallback(async () => {
    if (!enabled || !workspaceId || !apiUrl) {
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/health`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const health = await response.json();
        setSystemHealth(health);
        onSystemHealthLoaded?.(health);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError') {
        console.error('Failed to load system health:', err);
      }
    }
  }, [workspaceId, apiUrl, enabled, setSystemHealth, onSystemHealthLoaded]);

  const loadContextTokenCount = useCallback(async () => {
    if (!enabled || !workspaceId || !apiUrl) {
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/workbench/context-token-count`,
        {
          signal: controller.signal,
        }
      );
      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        const count = data.token_count || data.context_tokens || null;
        setContextTokenCount(count);
        onTokenCountLoaded?.(count);
      } else if (response.status === 404) {
        setContextTokenCount(null);
        onTokenCountLoaded?.(null);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError') {
        setContextTokenCount(null);
        onTokenCountLoaded?.(null);
      }
    }
  }, [workspaceId, apiUrl, enabled, setContextTokenCount, onTokenCountLoaded]);

  useEffect(() => {
    if (enabled && workspaceId && apiUrl) {
      loadWorkspaceInfo();
      loadSystemHealth();
    }
  }, [workspaceId, apiUrl, enabled, loadWorkspaceInfo, loadSystemHealth]);

  useEffect(() => {
    if (enabled && workspaceId && apiUrl && !messagesLoading) {
      loadContextTokenCount();
    }
  }, [workspaceId, apiUrl, enabled, messagesLoading, loadContextTokenCount]);

  return {
    workspaceTitle,
    systemHealth,
    contextTokenCount,
    loadWorkspaceInfo,
    loadSystemHealth,
    loadContextTokenCount,
  };
}


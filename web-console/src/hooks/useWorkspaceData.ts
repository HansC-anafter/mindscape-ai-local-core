'use client';

import { useCallback, useEffect } from 'react';
import { useWorkspaceMetadata } from '@/contexts/WorkspaceMetadataContext';
import { useMessages } from '@/contexts/MessagesContext';
import { isDocumentHidden, onDocumentVisible } from '@/lib/page-visibility';
import { sharedGetFetch } from '@/lib/resilient-fetch';

interface UseWorkspaceDataOptions {
  enabled?: boolean;
  loadSystemHealthOnMount?: boolean;
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
    setExecutorRuntime,
  } = useWorkspaceMetadata();

  const { messagesLoading } = useMessages();

  const {
    enabled = true,
    loadSystemHealthOnMount = true,
    onWorkspaceLoaded,
    onSystemHealthLoaded,
    onTokenCountLoaded,
  } = options || {};

  const loadWorkspaceInfo = useCallback(async () => {
    if (!enabled || !workspaceId || apiUrl == null || isDocumentHidden()) {
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    try {
      const [response, executorRouteResponse] = await Promise.all([
        sharedGetFetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
          method: 'GET',
          signal: controller.signal,
        }, { dedupKey: `workspace-details:${workspaceId}` }),
        sharedGetFetch(
          `${apiUrl}/api/v1/settings/model-route-registry/workspace-executor?workspace_id=${encodeURIComponent(workspaceId)}`,
          {
            method: 'GET',
            signal: controller.signal,
          },
          { dedupKey: `workspace-executor-route:${workspaceId}` },
        ).catch(() => null),
      ]);
      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        setWorkspaceTitle(data.title || data.name || '');
        if (executorRouteResponse && executorRouteResponse.ok) {
          const routeData = await executorRouteResponse.json();
          setExecutorRuntime(
            routeData.primary_executor_runtime || routeData.resolved_executor_runtime || null
          );
        }
        onWorkspaceLoaded?.(data);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError') {
        console.error('Failed to load workspace info:', err);
      }
    }
  }, [workspaceId, apiUrl, enabled, setWorkspaceTitle, setExecutorRuntime, onWorkspaceLoaded]);

  const loadSystemHealth = useCallback(async () => {
    if (!enabled || !workspaceId || apiUrl == null || isDocumentHidden()) {
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await sharedGetFetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/health`,
        { method: 'GET', signal: controller.signal },
        { dedupKey: `workspace-health:${workspaceId}` },
      );
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
    if (!enabled || !workspaceId || apiUrl == null || isDocumentHidden()) {
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    try {
      const response = await sharedGetFetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/workbench/context-token-count`,
        {
          method: 'GET',
          signal: controller.signal,
        },
        { dedupKey: `workspace-context-token-count:${workspaceId}` },
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
      if (loadSystemHealthOnMount) {
        loadSystemHealth();
      }
    }
  }, [workspaceId, apiUrl, enabled, loadSystemHealthOnMount, loadWorkspaceInfo, loadSystemHealth]);

  useEffect(() => onDocumentVisible(() => {
    if (!enabled || !workspaceId || !apiUrl) return;
    void loadWorkspaceInfo();
    if (loadSystemHealthOnMount) {
      void loadSystemHealth();
    }
    if (!messagesLoading) {
      void loadContextTokenCount();
    }
  }), [
    apiUrl,
    enabled,
    loadContextTokenCount,
    loadSystemHealth,
    loadSystemHealthOnMount,
    loadWorkspaceInfo,
    messagesLoading,
    workspaceId,
  ]);

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

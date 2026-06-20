'use client';

import React, {
  useState,
  useEffect,
  useCallback,
  useRef
} from 'react';

import { isDocumentHidden, onDocumentVisible } from '../lib/page-visibility';
import {
  WORKSPACE_READINESS_BACKGROUND_POLL_MS,
  WORKSPACE_READINESS_CACHE_MS,
  markWorkspaceReadinessAttempt,
  shouldRequestWorkspaceReadiness,
} from '../lib/workspace-readiness-policy';
import {
  fetchWorkspaceDetails,
  fetchWorkspaceExecutions,
  fetchWorkspaceHealth,
  fetchWorkspaceSummary,
  fetchWorkspaceTasks,
  updateWorkspaceRequest,
} from './workspace-data-context/api';
import {
  WorkspaceDataContext,
  useWorkspaceData,
  useWorkspaceDataOptional,
} from './workspace-data-context/context';
import type {
  ExecutionSession,
  SystemStatus,
  Task,
  Workspace,
  WorkspaceDataContextType,
  WorkspaceDataProviderProps,
} from './workspace-data-context/types';
import { useDebounce } from './workspace-data-context/useDebounce';

export type { WorkspaceDataInitialLoadProfile } from './workspace-data-context/types';
export { useWorkspaceData, useWorkspaceDataOptional };

const SYSTEM_STATUS_CACHE_MS = WORKSPACE_READINESS_CACHE_MS;

export function WorkspaceDataProvider({
  workspaceId,
  initialLoadProfile = 'full',
  children
}: WorkspaceDataProviderProps) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [executions, setExecutions] = useState<ExecutionSession[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);

  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(true);
  const [isLoadingWorkspaceDetails, setIsLoadingWorkspaceDetails] = useState(false);
  const [isLoadingTasks, setIsLoadingTasks] = useState(false);
  const [isLoadingExecutions, setIsLoadingExecutions] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const loadingWorkspaceRef = useRef(false);
  const loadingWorkspaceDetailsRef = useRef(false);
  const loadingTasksRef = useRef(false);
  const loadingExecutionsRef = useRef(false);
  const loadingSystemStatusRef = useRef(false);
  const systemStatusCacheRef = useRef<{ data: SystemStatus; timestamp: number } | null>(null);
  const mountedRef = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isCapabilityHostProfile = initialLoadProfile === 'capability-host';

  const loadWorkspace = useCallback(async () => {
    const tabId = `tab-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    if (workspaceId === 'new') {
      setIsLoadingWorkspace(false);
      return;
    }

    if (loadingWorkspaceRef.current) {
      return;
    }

    if (!mountedRef.current) {
      return;
    }

    loadingWorkspaceRef.current = true;
    setIsLoadingWorkspace(true);
    setError(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const timeoutId = setTimeout(() => {
      controller.abort();
    }, 15000);

    try {
      const data = await fetchWorkspaceSummary(workspaceId, controller.signal);
      clearTimeout(timeoutId);

      if (mountedRef.current) {
        if (!data || !data.id) {
          console.error(`[WorkspaceDataContext:${tabId}] Invalid workspace data received:`, data);
          setError('Workspace not found or invalid');
          setWorkspace(null);
        } else {
          setWorkspace(prev => (prev?.id === data.id ? { ...prev, ...data } : data));
          setError(null);
        }
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      console.error(`[WorkspaceDataContext:${tabId}] Error loading workspace:`, err);

      if (mountedRef.current) {
        if (err.name === 'AbortError') {
          console.error(`[WorkspaceDataContext:${tabId}] Request timeout loading workspace`);
          setError('Request timeout - please check if the backend is running');
        } else if (err.name === 'TypeError' && err.message.includes('fetch')) {
          console.error(`[WorkspaceDataContext:${tabId}] Network error loading workspace:`, err);
          setError('Network error - please check your connection');
        } else {
          console.error(`[WorkspaceDataContext:${tabId}] Failed to load workspace:`, err);
          setError(err.message || 'Failed to load workspace');
        }
        setWorkspace(null);
      }
    } finally {
      loadingWorkspaceRef.current = false;
      if (mountedRef.current) {
        setIsLoadingWorkspace(false);
      }
    }
  }, [workspaceId]);

  const loadWorkspaceDetails = useCallback(async () => {
    if (loadingWorkspaceDetailsRef.current || !mountedRef.current) return;
    if (!workspaceId || workspaceId === 'new') return;

    loadingWorkspaceDetailsRef.current = true;
    setIsLoadingWorkspaceDetails(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const data = await fetchWorkspaceDetails(workspaceId, controller.signal);
      clearTimeout(timeoutId);

      if (mountedRef.current && data?.id) {
        setWorkspace(prev => (prev?.id === data.id ? { ...prev, ...data } : data));
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError' && mountedRef.current) {
        console.error('[WorkspaceDataContext] Failed to load workspace details:', err);
      }
    } finally {
      loadingWorkspaceDetailsRef.current = false;
      if (mountedRef.current) {
        setIsLoadingWorkspaceDetails(false);
      }
    }
  }, [workspaceId]);

  const loadTasks = useCallback(async () => {
    if (loadingTasksRef.current || !mountedRef.current) return;
    if (isDocumentHidden()) return;
    if (!workspaceId || workspaceId === 'new') {
      return;
    }

    loadingTasksRef.current = true;
    setIsLoadingTasks(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    try {
      const nextTasks = await fetchWorkspaceTasks(workspaceId, controller.signal);
      clearTimeout(timeoutId);

      if (mountedRef.current && nextTasks !== null) {
        setTasks(nextTasks);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError' && mountedRef.current) {
        console.error('[WorkspaceDataContext] Failed to load tasks:', err);
      }
    } finally {
      loadingTasksRef.current = false;
      if (mountedRef.current) {
        setIsLoadingTasks(false);
      }
    }
  }, [workspaceId]);

  const loadExecutions = useCallback(async () => {
    if (loadingExecutionsRef.current || !mountedRef.current) return;
    if (isDocumentHidden()) return;

    loadingExecutionsRef.current = true;
    setIsLoadingExecutions(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    try {
      const mappedExecutions = await fetchWorkspaceExecutions(
        workspaceId,
        controller.signal
      );
      clearTimeout(timeoutId);

      if (mountedRef.current) {
        setExecutions(mappedExecutions);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError' && mountedRef.current) {
        console.error('[WorkspaceDataContext] Failed to load executions:', err);
      }
    } finally {
      loadingExecutionsRef.current = false;
      if (mountedRef.current) {
        setIsLoadingExecutions(false);
      }
    }
  }, [workspaceId]);

  const loadSystemStatus = useCallback(async (options?: { force?: boolean }) => {
    if (!mountedRef.current) return;
    if (loadingSystemStatusRef.current) return;
    if (isDocumentHidden()) return;

    const cached = systemStatusCacheRef.current;
    if (!options?.force && cached && Date.now() - cached.timestamp < SYSTEM_STATUS_CACHE_MS) {
      setSystemStatus(cached.data);
      return;
    }
    if (!shouldRequestWorkspaceReadiness(workspaceId, {
      force: options?.force,
      hasLocalSnapshot: Boolean(cached),
      minIntervalMs: SYSTEM_STATUS_CACHE_MS,
    })) {
      if (cached) setSystemStatus(cached.data);
      return;
    }

    loadingSystemStatusRef.current = true;
    markWorkspaceReadinessAttempt(workspaceId);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    try {
      const nextStatus = await fetchWorkspaceHealth(workspaceId, controller.signal);
      clearTimeout(timeoutId);

      if (!nextStatus) return;

      if (mountedRef.current) {
        systemStatusCacheRef.current = {
          data: nextStatus,
          timestamp: Date.now(),
        };
        setSystemStatus(nextStatus);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError') {
        console.error('[WorkspaceDataContext] Failed to load system status:', err);
      }
    } finally {
      loadingSystemStatusRef.current = false;
    }
  }, [workspaceId]);

  const refreshAll = useCallback(async () => {
    await Promise.all([
      loadWorkspace(),
      loadTasks(),
      loadExecutions(),
      loadSystemStatus({ force: true })
    ]);
  }, [loadWorkspace, loadTasks, loadExecutions, loadSystemStatus]);

  const debouncedRefresh = useDebounce(async () => {
    if (!mountedRef.current) return;
    await Promise.all([loadTasks(), loadExecutions()]);
    window.setTimeout(() => {
      if (mountedRef.current) void loadSystemStatus();
    }, 750);
  }, 2000);

  const updateWorkspace = useCallback(async (updates: Partial<Workspace>): Promise<Workspace | null> => {
    if (!workspace) return null;

    try {
      const updated = await updateWorkspaceRequest(workspaceId, updates);
      if (mountedRef.current) {
        setWorkspace(updated);
      }
      return updated;
    } catch (err: any) {
      console.error('[WorkspaceDataContext] Failed to update workspace:', err);
      return null;
    }
  }, [workspace, workspaceId]);

  useEffect(() => {
    mountedRef.current = true;
    loadingWorkspaceRef.current = false;
    loadingWorkspaceDetailsRef.current = false;
    loadingTasksRef.current = false;
    loadingExecutionsRef.current = false;
    loadingSystemStatusRef.current = false;
    systemStatusCacheRef.current = null;

    let isCancelled = false;

    const loadData = async () => {
      await new Promise(resolve => setTimeout(resolve, 100));

      if (!mountedRef.current || isCancelled) {
        return;
      }

      if (loadingWorkspaceRef.current) {
        return;
      }

      if (workspaceId === 'new') {
        setIsLoadingWorkspace(false);
        return;
      }

      if (isCapabilityHostProfile) {
        setIsLoadingWorkspace(false);
        return;
      }

      loadingWorkspaceRef.current = false;
      loadingWorkspaceDetailsRef.current = false;
      loadingTasksRef.current = false;
      loadingExecutionsRef.current = false;
      loadingSystemStatusRef.current = false;

      if (mountedRef.current) {
        let retries = 3;
        let success = false;
        while (retries > 0 && !success && mountedRef.current) {
          try {
            await loadWorkspace();
            success = true;
          } catch (err: any) {
            retries--;
            if (retries > 0) {
              console.warn(`[WorkspaceDataContext] Workspace load failed, retrying... (${retries} left)`, err);
              await new Promise(resolve => setTimeout(resolve, 1000));
            } else {
              console.error(`[WorkspaceDataContext] Workspace load failed after retries`, err);
            }
          }
        }
      }

      let auxiliaryLoadTimeoutId: ReturnType<typeof setTimeout> | null = null;
      let healthLoadTimeoutId: ReturnType<typeof setTimeout> | null = null;
      if (!isCapabilityHostProfile && mountedRef.current && workspaceId && workspaceId !== 'new') {
        auxiliaryLoadTimeoutId = setTimeout(() => {
          if (!mountedRef.current || isCancelled) return;
          void Promise.allSettled([
            loadTasks(),
            loadExecutions()
          ]).finally(() => {
            if (!mountedRef.current || isCancelled) return;
            healthLoadTimeoutId = setTimeout(() => {
              if (mountedRef.current && !isCancelled) void loadSystemStatus();
            }, 1200);
          });
        }, 750);
      }

      return () => {
        if (auxiliaryLoadTimeoutId) clearTimeout(auxiliaryLoadTimeoutId);
        if (healthLoadTimeoutId) clearTimeout(healthLoadTimeoutId);
      };
    };

    let cleanupScheduledLoads: (() => void) | undefined;
    void loadData().then((cleanup) => {
      if (typeof cleanup === 'function') {
        cleanupScheduledLoads = cleanup;
      }
    });

    return () => {
      isCancelled = true;
      mountedRef.current = false;
      cleanupScheduledLoads?.();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      loadingWorkspaceRef.current = false;
      loadingWorkspaceDetailsRef.current = false;
      loadingTasksRef.current = false;
      loadingExecutionsRef.current = false;
      loadingSystemStatusRef.current = false;
      setIsLoadingWorkspace(false);
      setIsLoadingWorkspaceDetails(false);
      setIsLoadingTasks(false);
      setIsLoadingExecutions(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, isCapabilityHostProfile]);

  useEffect(() => {
    if (isCapabilityHostProfile) return;
    const handleWorkspaceUpdate = (event?: Event) => {
      debouncedRefresh();
    };

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [debouncedRefresh, isCapabilityHostProfile]);

  useEffect(() => {
    if (isCapabilityHostProfile) return;
    if (!workspaceId || workspaceId === 'new') return;
    const interval = setInterval(() => {
      if (mountedRef.current && !isDocumentHidden()) loadSystemStatus();
    }, WORKSPACE_READINESS_BACKGROUND_POLL_MS);
    return () => clearInterval(interval);
  }, [workspaceId, loadSystemStatus, isCapabilityHostProfile]);

  useEffect(() => {
    if (isCapabilityHostProfile) return;
    if (!workspaceId || workspaceId === 'new') return;
    return onDocumentVisible(() => {
      if (!mountedRef.current) return;
      void Promise.allSettled([
        loadTasks(),
        loadExecutions(),
      ]).finally(() => {
        if (mountedRef.current) void loadSystemStatus();
      });
    });
  }, [workspaceId, loadTasks, loadExecutions, loadSystemStatus, isCapabilityHostProfile]);

  const isLoading = isLoadingWorkspace || isLoadingTasks || isLoadingExecutions;

  const value: WorkspaceDataContextType = {
    workspace,
    tasks,
    executions,
    systemStatus,
    isLoading,
    isLoadingWorkspace,
    isLoadingWorkspaceDetails,
    isLoadingTasks,
    isLoadingExecutions,
    error,
    refreshWorkspace: loadWorkspace,
    refreshWorkspaceDetails: loadWorkspaceDetails,
    refreshTasks: loadTasks,
    refreshExecutions: loadExecutions,
    refreshSystemStatus: loadSystemStatus,
    refreshAll,
    updateWorkspace
  };

  return (
    <WorkspaceDataContext.Provider value={value}>
      {children}
    </WorkspaceDataContext.Provider>
  );
}

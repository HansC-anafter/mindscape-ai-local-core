'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  getEffectiveWorkspaceProductConfiguration,
  replaceWorkspaceProductConfiguration,
  type ReplaceWorkspaceProductConfiguration,
  type WorkspaceCapabilitySetSnapshot,
  type WorkspaceProductScopeKind,
} from '@/lib/workspace-product-configuration-api';

interface WorkspaceCapabilitySetContextValue {
  snapshot: WorkspaceCapabilitySetSnapshot | null;
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<WorkspaceCapabilitySetSnapshot>;
  replace: (
    scopeKind: WorkspaceProductScopeKind,
    command: ReplaceWorkspaceProductConfiguration,
  ) => Promise<WorkspaceCapabilitySetSnapshot>;
}

const WorkspaceCapabilitySetContext = createContext<WorkspaceCapabilitySetContextValue | null>(null);

export function WorkspaceCapabilitySetProvider({
  workspaceId,
  activeGroupId,
  topologyRevision,
  children,
}: {
  workspaceId: string;
  activeGroupId?: string | null;
  topologyRevision?: number | null;
  children: React.ReactNode;
}) {
  const [snapshot, setSnapshot] = useState<WorkspaceCapabilitySetSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const next = await getEffectiveWorkspaceProductConfiguration({
        workspaceId,
        activeGroupId,
        topologyRevision,
        signal: controller.signal,
      });
      setSnapshot(next);
      return next;
    } catch (requestError) {
      if (!controller.signal.aborted) {
        const normalized = requestError instanceof Error
          ? requestError
          : new Error('workspace_product_request_failed');
        setError(normalized);
      }
      throw requestError;
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [activeGroupId, topologyRevision, workspaceId]);

  const replace = useCallback(async (
    scopeKind: WorkspaceProductScopeKind,
    command: ReplaceWorkspaceProductConfiguration,
  ) => {
    const next = await replaceWorkspaceProductConfiguration({
      workspaceId,
      activeGroupId,
      topologyRevision,
      scopeKind,
      command,
    });
    setSnapshot(next);
    setError(null);
    return next;
  }, [activeGroupId, topologyRevision, workspaceId]);

  useEffect(() => {
    void refresh().catch(() => undefined);
    return () => controllerRef.current?.abort();
  }, [refresh]);

  const value = useMemo<WorkspaceCapabilitySetContextValue>(() => ({
    snapshot,
    loading,
    error,
    refresh,
    replace,
  }), [error, loading, refresh, replace, snapshot]);

  return (
    <WorkspaceCapabilitySetContext.Provider value={value}>
      {children}
    </WorkspaceCapabilitySetContext.Provider>
  );
}

export function useWorkspaceCapabilitySet(): WorkspaceCapabilitySetContextValue {
  const value = useContext(WorkspaceCapabilitySetContext);
  if (!value) {
    throw new Error('WorkspaceCapabilitySetProvider is required');
  }
  return value;
}

export function useWorkspaceCapabilitySetOptional(): WorkspaceCapabilitySetContextValue | null {
  return useContext(WorkspaceCapabilitySetContext);
}

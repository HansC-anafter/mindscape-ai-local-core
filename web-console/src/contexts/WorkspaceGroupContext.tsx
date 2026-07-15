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

import { MindscapeAPIClient } from '@/api/client';
import { getApiBaseUrl } from '@/lib/api-url';


export interface WorkspaceGroupMember {
  workspace_id: string;
  role: 'dispatch' | 'cell';
  title?: string | null;
  visibility?: string | null;
  joined_at?: string | null;
}

export interface WorkspaceGroupTopology {
  id: string;
  display_name: string;
  revision: number;
  members: WorkspaceGroupMember[];
  role_map: Record<string, 'dispatch' | 'cell'>;
  is_ready: boolean;
}

interface WorkspaceGroupContextValue {
  groups: WorkspaceGroupTopology[];
  activeGroup: WorkspaceGroupTopology | null;
  activeRole: 'dispatch' | 'cell' | null;
  isLoading: boolean;
  error: string | null;
  selectGroup: (groupId: string | null) => void;
  refreshGroups: () => Promise<void>;
}

const ACTIVE_GROUP_KEY = 'mindscape.activeWorkspaceGroupId';
const WorkspaceGroupContext = createContext<WorkspaceGroupContextValue | null>(null);

export function WorkspaceGroupContextProvider({
  workspaceId,
  children,
}: {
  workspaceId: string;
  children: React.ReactNode;
}) {
  const [groups, setGroups] = useState<WorkspaceGroupTopology[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const refreshGroups = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const client = MindscapeAPIClient.fromBaseUrl(getApiBaseUrl());
      const response = await client.get(
        '/api/v1/workspace-groups?limit=200',
        { signal: controller.signal },
      );
      if (!response.ok) {
        throw new Error(`workspace_group_load_failed:${response.status}`);
      }
      const payload = await response.json();
      const nextGroups = Array.isArray(payload?.groups) ? payload.groups : [];
      setGroups(nextGroups);

      const storedGroupId = window.sessionStorage.getItem(ACTIVE_GROUP_KEY);
      const selected = nextGroups.find(
        (group: WorkspaceGroupTopology) =>
          group.id === storedGroupId && Boolean(group.role_map?.[workspaceId]),
      );
      if (selected) {
        setActiveGroupId(selected.id);
      } else {
        window.sessionStorage.removeItem(ACTIVE_GROUP_KEY);
        setActiveGroupId(null);
      }
    } catch (caught) {
      if (controller.signal.aborted) return;
      setGroups([]);
      setActiveGroupId(null);
      setError(caught instanceof Error ? caught.message : 'workspace_group_load_failed');
    } finally {
      if (!controller.signal.aborted && requestRef.current === controller) {
        setIsLoading(false);
      }
    }
  }, [workspaceId]);

  useEffect(() => {
    void refreshGroups();
    return () => requestRef.current?.abort();
  }, [refreshGroups]);

  const eligibleGroups = useMemo(
    () => groups.filter((group) => Boolean(group.role_map?.[workspaceId])),
    [groups, workspaceId],
  );
  const activeGroup = useMemo(
    () => eligibleGroups.find((group) => group.id === activeGroupId) || null,
    [activeGroupId, eligibleGroups],
  );

  const selectGroup = useCallback((groupId: string | null) => {
    if (groupId === null) {
      window.sessionStorage.removeItem(ACTIVE_GROUP_KEY);
      setActiveGroupId(null);
      return;
    }
    const selected = eligibleGroups.find((group) => group.id === groupId);
    if (!selected) {
      throw new Error('workspace_group_selection_not_authorized');
    }
    window.sessionStorage.setItem(ACTIVE_GROUP_KEY, selected.id);
    setActiveGroupId(selected.id);
  }, [eligibleGroups]);

  const value = useMemo<WorkspaceGroupContextValue>(() => ({
    groups: eligibleGroups,
    activeGroup,
    activeRole: activeGroup?.role_map?.[workspaceId] || null,
    isLoading,
    error,
    selectGroup,
    refreshGroups,
  }), [activeGroup, eligibleGroups, error, isLoading, refreshGroups, selectGroup, workspaceId]);

  return (
    <WorkspaceGroupContext.Provider value={value}>
      {children}
    </WorkspaceGroupContext.Provider>
  );
}

export function useWorkspaceGroup(): WorkspaceGroupContextValue {
  const value = useContext(WorkspaceGroupContext);
  if (!value) {
    throw new Error('useWorkspaceGroup must be used within WorkspaceGroupContextProvider');
  }
  return value;
}

export function useWorkspaceGroupOptional(): WorkspaceGroupContextValue | null {
  return useContext(WorkspaceGroupContext);
}

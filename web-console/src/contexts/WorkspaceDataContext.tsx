'use client';

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  ReactNode
} from 'react';

// Get API URL - for 'use client' components, always use browser-accessible URL
// In browser, NEXT_PUBLIC_API_URL points to host's localhost
// This is evaluated at runtime, not module load time
const getApiUrl = () => {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

// Workspace data types
interface Workspace {
  id: string;
  title: string;
  description?: string;
  primary_project_id?: string;
  default_playbook_id?: string;
  default_locale?: string;
  mode?: string | null;
  execution_mode?: 'qa' | 'execution' | 'hybrid' | null;
  expected_artifacts?: string[];
  execution_priority?: 'low' | 'medium' | 'high' | null;
  data_sources?: any;
  associated_intent?: any;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  playbook_storage_config?: Record<string, any>;
  playbook_auto_execution_config?: Record<string, any>;
}

interface Task {
  id: string;
  workspace_id: string;
  pack_id?: string;
  playbook_id?: string;
  task_type?: string;
  status: string;
  title?: string;
  summary?: string;
  message_id?: string;
  created_at: string;
  updated_at?: string;
  data?: any;
  params?: any;
  result?: any;
}

interface ExecutionSession {
  execution_id: string;
  workspace_id: string;
  status: string;
  playbook_code?: string;
  trigger_source?: string;
  current_step_index: number;
  total_steps: number;
  paused_at?: string;
  origin_intent_label?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  steps?: any[];
  [key: string]: any;
}

interface SystemStatus {
  llm_configured: boolean;
  llm_provider?: string;
  vector_db_connected: boolean;
  tools: Record<string, any>;
  critical_issues_count: number;
  has_issues: boolean;
}

interface WorkspaceDataContextType {
  // Data
  workspace: Workspace | null;
  tasks: Task[];
  executions: ExecutionSession[];
  systemStatus: SystemStatus | null;

  // Loading states
  isLoading: boolean;
  isLoadingWorkspace: boolean;
  isLoadingTasks: boolean;
  isLoadingExecutions: boolean;

  // Error state
  error: string | null;

  // Actions
  refreshWorkspace: () => Promise<void>;
  refreshTasks: () => Promise<void>;
  refreshExecutions: () => Promise<void>;
  refreshAll: () => Promise<void>;
  updateWorkspace: (updates: Partial<Workspace>) => Promise<Workspace | null>;
}

const WorkspaceDataContext = createContext<WorkspaceDataContextType | null>(null);

// Debounce helper
function useDebounce<T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): T {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  return useCallback(
    ((...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args);
      }, delay);
    }) as T,
    [delay]
  );
}

interface WorkspaceDataProviderProps {
  workspaceId: string;
  children: ReactNode;
}

export function WorkspaceDataProvider({
  workspaceId,
  children
}: WorkspaceDataProviderProps) {
  // Data states
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [executions, setExecutions] = useState<ExecutionSession[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);

  // Loading states
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(true);
  const [isLoadingTasks, setIsLoadingTasks] = useState(false);
  const [isLoadingExecutions, setIsLoadingExecutions] = useState(false);

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Refs to prevent duplicate requests
  const loadingWorkspaceRef = useRef(false);
  const loadingTasksRef = useRef(false);
  const loadingExecutionsRef = useRef(false);
  const mountedRef = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load workspace data
  const loadWorkspace = useCallback(async () => {
    if (loadingWorkspaceRef.current || !mountedRef.current) return;

    // Ensure AbortController exists before making request
    if (!abortControllerRef.current) {
      abortControllerRef.current = new AbortController();
    }

    loadingWorkspaceRef.current = true;
    setIsLoadingWorkspace(true);
    setError(null); // Clear previous errors

    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}`,
        { signal: abortControllerRef.current.signal }
      );

      if (!response.ok) {
        const errorText = response.status === 404
          ? 'Workspace not found'
          : `Failed to load workspace: ${response.status}`;
        throw new Error(errorText);
      }

      const data = await response.json();
      if (mountedRef.current) {
        if (!data || !data.id) {
          // API returned success but no valid workspace data
          setError('Workspace not found or invalid');
          setWorkspace(null);
          setIsLoadingWorkspace(false);
        } else {
          setWorkspace(data);
          setError(null);
          setIsLoadingWorkspace(false);
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // AbortError is expected in React Strict Mode - retry after a short delay
        console.log('[WorkspaceDataContext] Workspace load aborted (likely React Strict Mode), will retry');
        // Reset ref to allow retry
        loadingWorkspaceRef.current = false;
        // Retry after a short delay if still mounted
        // Use a ref to store the retry function to avoid dependency issues
        if (mountedRef.current) {
          // Create a new AbortController for retry immediately
          abortControllerRef.current = new AbortController();
          setTimeout(() => {
            if (mountedRef.current && !loadingWorkspaceRef.current) {
              loadWorkspace();
            }
          }, 200); // Increased delay to 200ms for more stability
        }
        return; // Exit early, don't execute finally block
      } else {
        // Other errors - set error state
        if (mountedRef.current) {
          console.error('[WorkspaceDataContext] Failed to load workspace:', err);
          setError(err.message || 'Failed to load workspace');
          setWorkspace(null);
          setIsLoadingWorkspace(false);
        }
      }
    } finally {
      loadingWorkspaceRef.current = false;
    }
  }, [workspaceId]);

  // Load tasks
  const loadTasks = useCallback(async () => {
    if (loadingTasksRef.current || !mountedRef.current) return;

    loadingTasksRef.current = true;
    setIsLoadingTasks(true);

    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}/tasks?limit=20&include_completed=true`,
        { signal: abortControllerRef.current?.signal }
      );

      if (!response.ok) {
        if (response.status === 429) {
          console.warn('[WorkspaceDataContext] Rate limited, will retry later');
          return;
        }
        throw new Error(`Failed to load tasks: ${response.status}`);
      }

      const data = await response.json();
      if (mountedRef.current) {
        setTasks(data.tasks || []);
      }
    } catch (err: any) {
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

  // Load executions with steps (batch API)
  const loadExecutions = useCallback(async () => {
    if (loadingExecutionsRef.current || !mountedRef.current) return;

    loadingExecutionsRef.current = true;
    setIsLoadingExecutions(true);

    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}/executions-with-steps?limit=100&include_steps_for=active`,
        { signal: abortControllerRef.current?.signal }
      );

      if (!response.ok) {
        throw new Error(`Failed to load executions: ${response.status}`);
      }

      const data = await response.json();
      if (mountedRef.current) {
        setExecutions(data.executions || []);
      }
    } catch (err: any) {
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

  // Load system status (from health endpoint)
  const loadSystemStatus = useCallback(async () => {
    if (!mountedRef.current) return;

    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}/health`,
        { signal: abortControllerRef.current?.signal }
      );

      if (!response.ok) return;

      const data = await response.json();
      if (mountedRef.current) {
        setSystemStatus({
          llm_configured: data.llm_configured,
          llm_provider: data.llm_provider,
          vector_db_connected: data.vector_db_connected,
          tools: data.tools || {},
          critical_issues_count: data.issues?.filter((i: any) => i.severity === 'error')?.length || 0,
          has_issues: (data.issues?.length || 0) > 0
        });
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('[WorkspaceDataContext] Failed to load system status:', err);
      }
    }
  }, [workspaceId]);

  // Refresh all data
  const refreshAll = useCallback(async () => {
    await Promise.all([
      loadWorkspace(),
      loadTasks(),
      loadExecutions(),
      loadSystemStatus()
    ]);
  }, [loadWorkspace, loadTasks, loadExecutions, loadSystemStatus]);

  // Debounced refresh for event handlers (2 second debounce)
  const debouncedRefresh = useDebounce(async () => {
    if (!mountedRef.current) return;
    await Promise.all([loadTasks(), loadExecutions()]);
  }, 2000);

  // Update workspace
  const updateWorkspace = useCallback(async (updates: Partial<Workspace>): Promise<Workspace | null> => {
    if (!workspace) return null;

    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updates)
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to update workspace: ${response.status}`);
      }

      const updated = await response.json();
      if (mountedRef.current) {
        setWorkspace(updated);
      }
      return updated;
    } catch (err: any) {
      console.error('[WorkspaceDataContext] Failed to update workspace:', err);
      return null;
    }
  }, [workspace, workspaceId]);

  // Initial load
  useEffect(() => {
    mountedRef.current = true;
    // Create new AbortController for this effect run
    abortControllerRef.current = new AbortController();

    // Load data sequentially to avoid rate limiting
    const loadData = async () => {
      await loadWorkspace();
      await new Promise(resolve => setTimeout(resolve, 100));
      await loadTasks();
      await new Promise(resolve => setTimeout(resolve, 100));
      await loadExecutions();
      await loadSystemStatus();
    };

    loadData();

    return () => {
      mountedRef.current = false;
      // Abort any pending requests when component unmounts or workspaceId changes
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]); // Only depend on workspaceId to avoid unnecessary re-renders

  // Listen for workspace events (unified event handling)
  useEffect(() => {
    const handleWorkspaceUpdate = (event?: Event) => {
      if (process.env.NODE_ENV === 'development') {
        const customEvent = event as CustomEvent;
        console.log('[WorkspaceDataContext] Received workspace update event:', customEvent?.type, customEvent?.detail || 'no detail');
      }
      debouncedRefresh();
    };

    // Listen to all workspace-related events with single handler
    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [debouncedRefresh]);

  const isLoading = isLoadingWorkspace || isLoadingTasks || isLoadingExecutions;

  const value: WorkspaceDataContextType = {
    workspace,
    tasks,
    executions,
    systemStatus,
    isLoading,
    isLoadingWorkspace,
    isLoadingTasks,
    isLoadingExecutions,
    error,
    refreshWorkspace: loadWorkspace,
    refreshTasks: loadTasks,
    refreshExecutions: loadExecutions,
    refreshAll,
    updateWorkspace
  };

  return (
    <WorkspaceDataContext.Provider value={value}>
      {children}
    </WorkspaceDataContext.Provider>
  );
}

// Hook to use workspace data
export function useWorkspaceData(): WorkspaceDataContextType {
  const context = useContext(WorkspaceDataContext);
  if (!context) {
    throw new Error('useWorkspaceData must be used within a WorkspaceDataProvider');
  }
  return context;
}

// Optional hook that returns null if not in provider (for components that may or may not be in workspace context)
export function useWorkspaceDataOptional(): WorkspaceDataContextType | null {
  return useContext(WorkspaceDataContext);
}


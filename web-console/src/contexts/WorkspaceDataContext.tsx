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
import { getApiBaseUrl, getApiUrl as getDynamicApiUrl } from '../lib/api-url';

// This is evaluated at runtime, not module load time
// Use synchronous version for immediate use, but prefer async version when possible
const getApiUrl = () => {
  return getApiBaseUrl();
};

// Workspace data types
interface Workspace {
  id: string;
  title: string;
  description?: string;
  workspace_type?: 'personal' | 'brand' | 'team';
  primary_project_id?: string;
  default_playbook_id?: string;
  default_locale?: string;
  mode?: string | null;
  execution_mode?: 'qa' | 'execution' | 'hybrid' | 'meeting' | null;
  expected_artifacts?: string[];
  execution_priority?: 'low' | 'medium' | 'high' | null;
  data_sources?: any;
  associated_intent?: any;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  playbook_storage_config?: Record<string, any>;
  playbook_auto_execution_config?: Record<string, any>;
  workspace_blueprint?: {
    instruction?: {
      persona?: string;
      goals?: string[];
      anti_goals?: string[];
      style_rules?: string[];
      domain_context?: string;
      version?: number;
    };
    brief?: string;
    [key: string]: any;
  };
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

  // Load workspace data with timeout
  const loadWorkspace = useCallback(async () => {
    const tabId = `tab-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    // Skip loading for 'new' workspace (wizard mode)
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
    setError(null); // Clear previous errors

    // Abort any existing requests first
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Create new abort controller for this request
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const timeoutId = setTimeout(() => {
      controller.abort();
    }, 30000); // 30 second timeout (backend may be under heavy load)

    try {
      const startTime = Date.now();

      // Use a unique request ID to avoid browser request deduplication
      const requestId = `req-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

      // Directly use base URL to avoid any blocking from getDynamicApiUrl
      // This ensures the fetch request can be sent immediately
      const apiUrl = getApiBaseUrl();
      const url = `${apiUrl}/api/v1/workspaces/${workspaceId}?t=${requestId}`;

      let response: Response;
      try {
        // Configure request timeout protection
        // Use a shorter timeout to fail fast if there's a network issue
        // Fetch with minimal config to avoid CORS preflight
        // Use same-origin mode since frontend and backend are on different ports
        const fetchPromise = fetch(url, {
          method: 'GET',
          signal: controller.signal,
          // Configure fetch for same-origin requests
          cache: 'no-store',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
        });

        // Execute fetch request
        response = await fetchPromise;
      } catch (fetchErr: any) {
        // If it's a timeout or abort, provide clearer error message
        if (fetchErr.name === 'AbortError' || fetchErr.message?.includes('timeout')) {
          throw new Error('Request timeout - backend may be unreachable or slow to respond');
        }
        throw fetchErr;
      }

      clearTimeout(timeoutId);

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
          console.error(`[WorkspaceDataContext:${tabId}] Invalid workspace data received:`, data);
          setError('Workspace not found or invalid');
          setWorkspace(null);
        } else {
          setWorkspace(data);
          setError(null);
        }
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      console.error(`[WorkspaceDataContext:${tabId}] Error loading workspace:`, err);

      if (mountedRef.current) {
        // Handle abort/timeout error
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

  // Load tasks with timeout
  const loadTasks = useCallback(async () => {
    if (loadingTasksRef.current || !mountedRef.current) return;
    if (!workspaceId || workspaceId === 'new') {
      return;
    }

    loadingTasksRef.current = true;
    setIsLoadingTasks(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}/tasks?limit=20&include_completed=true`,
        { signal: controller.signal }
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        if (response.status === 429) {
          console.warn('[WorkspaceDataContext] Rate limited, will retry later');
          return;
        }
        throw new Error(`Failed to load tasks: ${response.status}`);
      }

      const data = await response.json();
      if (mountedRef.current) {
        const tasks = data.tasks || [];
        setTasks(tasks);
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

  // Load executions with steps (batch API) with timeout
  const loadExecutions = useCallback(async () => {
    if (loadingExecutionsRef.current || !mountedRef.current) return;

    loadingExecutionsRef.current = true;
    setIsLoadingExecutions(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

    try {
      // Optimization: use /tasks endpoint (which we patched to strip heavy results)
      // instead of /executions-with-steps (which returns huge payloads).
      // This prevents the "Infinite Loading" issue.
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}/tasks?limit=100&include_completed=true&task_type=execution`,
        { signal: controller.signal }
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Failed to load executions: ${response.status}`);
      }

      const data = await response.json();
      if (mountedRef.current) {
        // Map Task to ExecutionSession
        const mappedExecutions = (data.tasks || []).map((t: any) => ({
          execution_id: t.id,
          status: t.status,
          workspace_id: t.workspace_id,
          project_id: t.project_id,
          playbook_code: t.pack_id, // Map pack_id to playbook_code
          created_at: t.created_at,
          started_at: t.started_at,
          completed_at: t.completed_at,
          current_step_index: 0,
          total_steps: 0,
          task: t,
          steps: [] // Steps are lazy loaded via SSE or detail view
        }));
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

  // Load system status (from health endpoint) with timeout
  const loadSystemStatus = useCallback(async () => {
    if (!mountedRef.current) return;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/workspaces/${workspaceId}/health`,
        { signal: controller.signal }
      );

      clearTimeout(timeoutId);

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
      clearTimeout(timeoutId);
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
    await Promise.all([loadTasks(), loadExecutions(), loadSystemStatus()]);
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
    // Reset all loading flags when workspaceId changes
    mountedRef.current = true;
    loadingWorkspaceRef.current = false;
    loadingTasksRef.current = false;
    loadingExecutionsRef.current = false;

    // Track loading state to prevent duplicate loads during hot reload
    let isCancelled = false;

    // Delay to ensure cleanup completion
    const loadData = async () => {
      // Wait a bit to ensure any previous loads are cleared
      await new Promise(resolve => setTimeout(resolve, 100));

      // Double-check we're still mounted and not already loading
      if (!mountedRef.current || isCancelled) {
        return;
      }

      // Check if already loading to prevent duplicate loads during hot reload
      if (loadingWorkspaceRef.current) {
        return;
      }

      // Skip loading for 'new' workspace (wizard mode)
      if (workspaceId === 'new') {
        setIsLoadingWorkspace(false);
        return;
      }

      // Reset flags to ensure fresh start
      loadingWorkspaceRef.current = false;
      loadingTasksRef.current = false;
      loadingExecutionsRef.current = false;

      // Load workspace first (most important) - with retry logic
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

      // Load other data in parallel after workspace loads
      // Use workspaceId instead of workspace state since state updates are async
      if (mountedRef.current && workspaceId && workspaceId !== 'new') {
        await new Promise(resolve => setTimeout(resolve, 300));
        await Promise.all([
          loadTasks(),
          loadExecutions(),
          loadSystemStatus()
        ]);
      }
    };

    loadData();

    return () => {
      isCancelled = true;
      mountedRef.current = false;
      // Abort any pending requests
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      // Clear loading flags on unmount
      loadingWorkspaceRef.current = false;
      loadingTasksRef.current = false;
      loadingExecutionsRef.current = false;
      setIsLoadingWorkspace(false);
      setIsLoadingTasks(false);
      setIsLoadingExecutions(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  // Listen for workspace events (unified event handling)
  useEffect(() => {
    const handleWorkspaceUpdate = (event?: Event) => {
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

  // Poll system status every 60s for live monitoring
  useEffect(() => {
    if (!workspaceId || workspaceId === 'new') return;
    const interval = setInterval(() => {
      if (mountedRef.current) loadSystemStatus();
    }, 60_000);
    return () => clearInterval(interval);
  }, [workspaceId, loadSystemStatus]);

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

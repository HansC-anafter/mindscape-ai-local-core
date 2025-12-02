'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '../../../components/Header';
import WorkspaceChat from '../../../components/WorkspaceChat';
import MindscapeAIWorkbench from '../../../components/MindscapeAIWorkbench';
import ResearchModePanel from '../../../components/ResearchModePanel';
import PublishingModePanel from '../../../components/PublishingModePanel';
import PlanningModePanel from '../../../components/PlanningModePanel';
import IntegratedSystemStatusCard from '../../../components/IntegratedSystemStatusCard';
import WorkspaceHeader from '../components/WorkspaceHeader';
import WorkspaceScopePanel from '../components/WorkspaceScopePanel';
import TimelinePanel from '../components/TimelinePanel';
import PendingTasksPanel from '../components/PendingTasksPanel';
import LeftSidebarTabs from './components/LeftSidebarTabs';
import OutcomesPanel, { Artifact } from './components/OutcomesPanel';
import OutcomeDetailModal from '../components/OutcomeDetailModal';
import BackgroundTasksPanel from '../components/BackgroundTasksPanel';
import { WorkspaceMode } from '../../../components/WorkspaceModeSelector';
import { t } from '@/lib/i18n';
import ConfirmDialog from '../../../components/ConfirmDialog';
import HelpIcon from '../../../components/HelpIcon';
import ExecutionInspector from '../components/ExecutionInspector';
import ExecutionChatPanel from '../components/ExecutionChatPanel';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface DataSource {
  local_folder?: string;
  obsidian_vault?: string;
  wordpress?: string;
  rag_source?: string;
}

interface AssociatedIntent {
  id: string;
  title: string;
  tags?: string[];
  status?: string;
  priority?: string;
}

interface Workspace {
  id: string;
  title: string;
  description?: string;
  primary_project_id?: string;
  default_playbook_id?: string;
  default_locale?: string;
  mode?: WorkspaceMode;
  data_sources?: DataSource | null;
  associated_intent?: AssociatedIntent | null;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  playbook_storage_config?: Record<string, { base_path?: string; artifacts_dir?: string }>;
}

interface PendingTask {
  execution_id: string;
  playbook_code: string;
  status: string;
  timestamp: string;
  message?: string;
}

export default function WorkspacePage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;

  if (!workspaceId) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-gray-500">{t('workspaceNotFound')}</div>
        </div>
      </div>
    );
  }

  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [pendingTasks, setPendingTasks] = useState<PendingTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rightSidebarTab, setRightSidebarTab] = useState<'timeline' | 'workbench'>('timeline');
  const [leftSidebarTab, setLeftSidebarTab] = useState<'timeline' | 'outcomes' | 'background'>('timeline');
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [updatingMode, setUpdatingMode] = useState(false);
  const [systemStatus, setSystemStatus] = useState<any>(null);
  const [workbenchRefreshTrigger, setWorkbenchRefreshTrigger] = useState(0);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [focusExecutionId, setFocusExecutionId] = useState<string | null>(null);
  const [focusedExecution, setFocusedExecution] = useState<any>(null);
  const [focusedPlaybookMetadata, setFocusedPlaybookMetadata] = useState<any>(null);
  const [showSystemTools, setShowSystemTools] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const loadingRef = useRef(false);
  const pendingRequestsRef = useRef<Set<string>>(new Set());
  const loadedWorkspaceIdRef = useRef<string | null>(null);

  // Helper function to handle 429 errors with retry - stops immediately on 429
  const fetchWithRetry = useCallback(async (url: string, options: RequestInit = {}, retries = 2): Promise<Response | null> => {
    const requestKey = `${url}-${JSON.stringify(options)}`;

    // Clear stale requests on Fast Refresh or component remount
    if (pendingRequestsRef.current.has(requestKey)) {
      console.log('[fetchWithRetry] Request already pending, clearing and retrying:', requestKey);
      pendingRequestsRef.current.delete(requestKey);
    }

    pendingRequestsRef.current.add(requestKey);

    try {
      for (let i = 0; i < retries; i++) {
        try {
          const response = await fetch(url, {
            ...options,
            signal: abortControllerRef.current?.signal
          });

          if (response.status === 429) {
            pendingRequestsRef.current.delete(requestKey);
            const retryAfter = Math.max(parseInt(response.headers.get('Retry-After') || '10', 10), 10);
            console.error(`Rate limited (429) for ${url}, stopping all requests. Retry after ${retryAfter}s`);
            pendingRequestsRef.current.clear();

            if (isMountedRef.current) {
              const errorMessage = t('rateLimitExceeded', { seconds: retryAfter });
              setError(errorMessage);
              setLoading(false);
              loadingRef.current = false;
              loadedWorkspaceIdRef.current = null;
            }

            return null;
          }

          if (response.ok || response.status < 500) {
            pendingRequestsRef.current.delete(requestKey);
            return response;
          }

          if (i < retries - 1) {
            await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
          }
        } catch (err: any) {
          if (err.name === 'AbortError') {
            pendingRequestsRef.current.delete(requestKey);
            return null;
          }
          if (i === retries - 1) {
            pendingRequestsRef.current.delete(requestKey);
            throw err;
          }
          await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
        }
      }
    } finally {
      pendingRequestsRef.current.delete(requestKey);
    }

    return null;
  }, []);

  // Load workspace function - available for both initial load and manual refresh
  const loadWorkspace = useCallback(async () => {
    console.log('[loadWorkspace] Starting, workspaceId:', workspaceId, 'mounted:', isMountedRef.current);
    if (!isMountedRef.current) {
      console.log('[loadWorkspace] Component not mounted, returning');
      return;
    }
    try {
      console.log('[loadWorkspace] Calling fetchWithRetry...');
      let response = await fetchWithRetry(`${API_URL}/api/v1/workspaces/${workspaceId}`);
      console.log('[loadWorkspace] fetchWithRetry response:', response ? `Status: ${response.status}, OK: ${response.ok}` : 'null');

      if (!response) {
        console.warn('[loadWorkspace] fetchWithRetry returned null, trying direct fetch for workspace', workspaceId);
        try {
          // Clear pending request before direct fetch
          const directRequestKey = `${API_URL}/api/v1/workspaces/${workspaceId}-{}`;
          pendingRequestsRef.current.delete(directRequestKey);

          response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}`, {
            signal: abortControllerRef.current?.signal
          });
          console.log('[loadWorkspace] Direct fetch response:', response ? `Status: ${response.status}, OK: ${response.ok}` : 'null');
        } catch (fetchErr: any) {
          console.error('[loadWorkspace] Direct fetch failed:', fetchErr);
          if (fetchErr.name === 'AbortError') {
            console.log('[loadWorkspace] Request aborted');
            return;
          }
          if (isMountedRef.current) {
            setError(t('failedToLoadWorkspace'));
            setLoading(false);
            loadingRef.current = false;
          }
          return;
        }
      }

      if (!response) {
        console.error('[loadWorkspace] No response after all attempts');
        if (isMountedRef.current) {
          setError(t('failedToLoadWorkspace'));
          setLoading(false);
          loadingRef.current = false;
        }
        return;
      }

      if (!isMountedRef.current) {
        console.log('[loadWorkspace] Component unmounted before processing response');
        return;
      }

      if (response.ok) {
        console.log('[loadWorkspace] Response OK, parsing JSON...');
        try {
          const data = await response.json();
          console.log('[loadWorkspace] Data parsed successfully:', data?.id, data?.title);
          if (isMountedRef.current) {
            console.log('[loadWorkspace] Setting workspace state...');
            setWorkspace(data);
            setError(null);
            console.log('[loadWorkspace] Workspace state updated successfully');
          } else {
            console.log('[loadWorkspace] Component unmounted, skipping state update');
          }
        } catch (jsonErr) {
          console.error('[loadWorkspace] JSON parse error:', jsonErr);
          if (isMountedRef.current) {
            setError(t('failedToLoadWorkspace'));
            setLoading(false);
            loadingRef.current = false;
          }
        }
      } else {
        console.error('[loadWorkspace] Response not OK:', response.status, response.statusText);
        if (isMountedRef.current) {
          const errorText = response.status === 404 ? t('workspaceNotFound') : t('failedToLoadWorkspace');
          setError(errorText);
          setLoading(false);
          loadingRef.current = false;
        }
      }
    } catch (err: any) {
      console.error('[loadWorkspace] Exception caught:', err, 'name:', err?.name, 'message:', err?.message);
      if (!isMountedRef.current || err.name === 'AbortError') {
        console.log('[loadWorkspace] Component unmounted or aborted, returning');
        return;
      }
      setError(t('failedToLoadWorkspace'));
      setLoading(false);
      loadingRef.current = false;
    }
  }, [workspaceId, fetchWithRetry]);

  // Load tasks function
  const loadTasks = useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const response = await fetchWithRetry(
        `${API_URL}/api/v1/workspaces/${workspaceId}/tasks?limit=10`
      );
      if (!response || !isMountedRef.current) return;

      if (response.ok) {
        const data = await response.json();
        if (isMountedRef.current) {
          setPendingTasks(data.tasks || []);
        }
      }
    } catch (err: any) {
      if (!isMountedRef.current || err.name === 'AbortError') return;
      console.error('Failed to load tasks:', err);
    }
  }, [workspaceId, fetchWithRetry]);

  // Load system status function - now uses dedicated health endpoint to avoid duplicate workbench calls
  // MindscapeAIWorkbench component already calls /workbench API, so we use /health for system status only
  const loadSystemStatus = useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const response = await fetchWithRetry(`${API_URL}/api/v1/workspaces/${workspaceId}/health`);
      if (!response || !isMountedRef.current) return;

      if (response.ok) {
        const data = await response.json();
        if (isMountedRef.current) {
          // Transform health data to match system_status format
          setSystemStatus({
            llm_configured: data.llm_configured,
            llm_provider: data.llm_provider,
            vector_db_connected: data.vector_db_connected,
            tools: data.tools || {},
            critical_issues_count: data.issues?.filter((i: any) => i.severity === 'error')?.length || 0,
            has_issues: (data.issues?.length || 0) > 0
          });
        }
      }
    } catch (err: any) {
      if (!isMountedRef.current || err.name === 'AbortError') return;
      console.error('Failed to load system status:', err);
    }
  }, [workspaceId, fetchWithRetry]);

  // Listen for open-execution-inspector event
  useEffect(() => {
    const handleOpenExecutionInspector = (event: CustomEvent) => {
      const { executionId } = event.detail;
      if (executionId) {
        setSelectedExecutionId(executionId);
        setFocusExecutionId(executionId); // Set focus mode
      }
    };

    // Listen for clear-focus event to return to workspace overview
    const handleClearFocus = () => {
      setFocusExecutionId(null);
      setSelectedExecutionId(null);
    };

    window.addEventListener('open-execution-inspector', handleOpenExecutionInspector as EventListener);
    window.addEventListener('clear-execution-focus', handleClearFocus as EventListener);
    return () => {
      window.removeEventListener('open-execution-inspector', handleOpenExecutionInspector as EventListener);
      window.removeEventListener('clear-execution-focus', handleClearFocus as EventListener);
    };
  }, []);

  // Load focused execution and playbook metadata when focusExecutionId changes
  useEffect(() => {
    if (!focusExecutionId || !workspaceId) {
      setFocusedExecution(null);
      setFocusedPlaybookMetadata(null);
      return;
    }

    const loadFocusedExecution = async () => {
      try {
        // Load execution
        const execResponse = await fetch(
          `${API_URL}/api/v1/workspaces/${workspaceId}/executions/${focusExecutionId}`
        );
        if (execResponse.ok) {
          const execData = await execResponse.json();
          setFocusedExecution(execData);

          // Load playbook metadata if playbook_code exists
          if (execData.playbook_code) {
            try {
              const playbookResponse = await fetch(
                `${API_URL}/api/v1/playbooks/${execData.playbook_code}`
              );
              if (playbookResponse.ok) {
                const playbookData = await playbookResponse.json();
                setFocusedPlaybookMetadata(playbookData);
              } else {
                // Use basic metadata from execution
                setFocusedPlaybookMetadata({
                  playbook_code: execData.playbook_code || '',
                  version: execData.playbook_version || '1.0.0'
                });
              }
            } catch (err) {
              // Use basic metadata from execution
              setFocusedPlaybookMetadata({
                playbook_code: execData.playbook_code || '',
                version: execData.playbook_version || '1.0.0'
              });
            }
          }
        }
      } catch (err) {
        console.error('Failed to load focused execution:', err);
        setFocusedExecution(null);
        setFocusedPlaybookMetadata(null);
      }
    };

    loadFocusedExecution();
  }, [focusExecutionId, workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;

    const currentWorkspaceId = workspaceId;

    if (loadingRef.current && loadedWorkspaceIdRef.current === currentWorkspaceId) {
      console.log('Already loading workspace, skipping:', currentWorkspaceId);
      return;
    }

    console.log('[useEffect] Loading workspace:', currentWorkspaceId, 'current workspace:', workspace?.id, 'API_URL:', API_URL);
    loadedWorkspaceIdRef.current = currentWorkspaceId;
    isMountedRef.current = true;
    loadingRef.current = true;
    setLoading(true);
    setError(null);

    // Cancel any pending requests from previous effect run
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    // Create abort controller for this effect run
    abortControllerRef.current = new AbortController();

    // Load data sequentially to avoid rate limiting
    const loadData = async () => {
      try {
        if (!isMountedRef.current) {
          loadingRef.current = false;
          setLoading(false);
          return;
        }

        await loadWorkspace();

        if (!isMountedRef.current) {
          loadingRef.current = false;
          setLoading(false);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 500));

        if (loadedWorkspaceIdRef.current !== currentWorkspaceId) {
          loadingRef.current = false;
          setLoading(false);
          return;
        }
        await loadTasks();

        if (!isMountedRef.current) {
          loadingRef.current = false;
          setLoading(false);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 500));

        if (loadedWorkspaceIdRef.current !== currentWorkspaceId) {
          loadingRef.current = false;
          setLoading(false);
          return;
        }
        await loadSystemStatus();

        if (isMountedRef.current && loadedWorkspaceIdRef.current === currentWorkspaceId) {
          loadingRef.current = false;
          setLoading(false);
        }
      } catch (err) {
        console.error('[loadData] Failed to load workspace data:', err);
        if (isMountedRef.current) {
          loadingRef.current = false;
          setLoading(false);
          if (!error) {
            setError(t('failedToLoadWorkspace'));
          }
        }
      }
    };

    loadData();

    return () => {
      isMountedRef.current = false;
      loadingRef.current = false;
      pendingRequestsRef.current.clear();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [workspaceId, loadWorkspace, loadTasks, loadSystemStatus]);


  const handleModeChange = async (mode: WorkspaceMode) => {
    if (!workspace) return;

    try {
      setUpdatingMode(true);
      // Explicitly send null to clear mode
      const response = await fetch(
        `${API_URL}/api/v1/workspaces/${workspaceId}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ mode: mode === null ? null : mode }),
        }
      );

      if (response.ok) {
        const updated = await response.json();
        setWorkspace(updated);
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error('Failed to update workspace mode:', errorData);
      }
    } catch (err) {
      console.error('Failed to update workspace mode:', err);
    } finally {
      setUpdatingMode(false);
    }
  };

  // Auto-execute playbook when workspace is loaded with auto_execute_playbook parameter
  useEffect(() => {
    if (!workspace || loading) return;

    const searchParams = new URLSearchParams(window.location.search);
    const autoExecute = searchParams.get('auto_execute_playbook') === 'true';
    const variantId = searchParams.get('variant_id');

    if (autoExecute && workspace.default_playbook_id) {
      const executePlaybook = async () => {
        try {
          const actionParams: any = {
            playbook_code: workspace.default_playbook_id
          };

          if (variantId) {
            actionParams.variant_id = variantId;
          }

          const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              action: 'execute_playbook',
              action_params: actionParams
            })
          });

          if (!response.ok) {
            throw new Error('Failed to execute playbook');
          }

          // Clear URL parameters to avoid re-execution on refresh
          const newUrl = new URL(window.location.href);
          newUrl.searchParams.delete('auto_execute_playbook');
          newUrl.searchParams.delete('variant_id');
          window.history.replaceState({}, '', newUrl.toString());

          // Trigger workspace chat update event to refresh messages
          window.dispatchEvent(new Event('workspace-chat-updated'));
        } catch (err: any) {
          console.error('Failed to auto-execute playbook:', err);
        }
      };

      // Small delay to ensure workspace chat is ready
      const timer = setTimeout(executePlaybook, 500);
      return () => clearTimeout(timer);
    }
  }, [workspace, workspaceId, loading]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-gray-500">{t('loadingWorkspace')}</div>
        </div>
      </div>
    );
  }

  if (error || (!workspace && !loading)) {
    console.log('Rendering error state:', { error, workspace: workspace?.id, loading });
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-center">
            <div className="text-red-500 mb-4">{error || t('workspaceNotFound')}</div>
            {error && error.includes('Rate limit') && (
              <button
                onClick={() => {
                  setError(null);
                  loadingRef.current = false;
                  loadedWorkspaceIdRef.current = null;
                  setLoading(true);
                  loadWorkspace();
                }}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                {t('retryButton')}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />

      <div className="flex flex-col h-[calc(100vh-48px)]">
        {/* Workspace Header - Middle Top with Mode Selector */}
        {workspace && (
          <WorkspaceHeader
            workspaceName={workspace.title}
            mode={workspace.mode || null}
            associatedIntent={workspace.associated_intent}
            workspaceId={workspaceId}
            onModeChange={handleModeChange}
            updatingMode={updatingMode}
            onWorkspaceUpdate={loadWorkspace}
            apiUrl={API_URL}
          />
        )}

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar - Tab Panel and Workspace Scope Panel */}
          <div className="w-80 border-r bg-white flex flex-col">
            {/* Tab Panel Section - Top */}
            <div className="flex-1 overflow-hidden min-h-0">
              <LeftSidebarTabs
                activeTab={leftSidebarTab}
                onTabChange={setLeftSidebarTab}
                timelineContent={
                  <TimelinePanel
                    workspaceId={workspaceId}
                    apiUrl={API_URL}
                    isInSettingsPage={rightSidebarTab === 'settings'}
                    focusExecutionId={focusExecutionId}
                    onClearFocus={() => {
                      setFocusExecutionId(null);
                      setSelectedExecutionId(null);
                      // Also dispatch event to ensure all components are notified
                      window.dispatchEvent(new CustomEvent('clear-execution-focus'));
                    }}
                  />
                }
                outcomesContent={
                  <OutcomesPanel
                    workspaceId={workspaceId}
                    apiUrl={API_URL}
                    onArtifactClick={setSelectedArtifact}
                  />
                }
                backgroundContent={
                  <BackgroundTasksPanel
                    workspaceId={workspaceId}
                    apiUrl={API_URL}
                  />
                }
              />
            </div>

            {/* Workspace Scope Panel - Bottom (Data Sources only, compact layout) */}
            {workspace && (
              <div className="border-t bg-orange-50/30 mt-auto">
                <WorkspaceScopePanel
                  dataSources={workspace.data_sources}
                  workspaceId={workspaceId}
                  apiUrl={API_URL}
                  workspace={workspace}
                />
              </div>
            )}
          </div>

          {/* Main Area - Execution Inspector or Workspace Chat */}
          <div className="flex-1 flex flex-col" style={{ minWidth: 0, overflow: 'hidden' }}>
            {selectedExecutionId ? (
              <ExecutionInspector
                executionId={selectedExecutionId}
                workspaceId={workspaceId}
                apiUrl={API_URL}
                onClose={() => {
                  setSelectedExecutionId(null);
                  setFocusExecutionId(null); // Clear focus mode
                  // Dispatch event to ensure all components are notified
                  window.dispatchEvent(new CustomEvent('clear-execution-focus'));
                }}
              />
            ) : (
              <WorkspaceChat
                workspaceId={workspaceId}
                apiUrl={API_URL}
                onFileAnalyzed={() => {
                  // Refresh workbench when file is analyzed
                  setWorkbenchRefreshTrigger(prev => prev + 1);
                }}
              />
            )}
          </div>

          {/* Right Sidebar - Execution Chat (when focused) or Workspace Tools (default) */}
          <div className="w-80 border-l bg-white flex flex-col">
            {/* Header - Title with AI Team Collaborating and settings icon */}
            <div className="flex items-center justify-between border-b bg-gray-50 px-3 py-1.5">
              <div className="flex items-center gap-2 flex-1">
                <h3 className="text-xs font-bold bg-gradient-to-r from-blue-500 to-purple-600 text-white px-2 py-0.5 rounded-lg shadow-md border border-blue-300 flex-shrink-0">
                  {t('mindscapeAIWorkbench')}
                </h3>
                <div className="h-3 w-px bg-gray-300"></div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <h3 className="text-xs font-semibold text-gray-900">
                    {focusExecutionId
                      ? (focusedPlaybookMetadata?.title || focusedExecution?.playbook_code || t('playbookConversation'))
                      : t('aiTeamCollaborating')
                    }
                  </h3>
                  {!focusExecutionId && <HelpIcon helpKey="aiTeamCollaboratingHelp" />}
                </div>
              </div>
              {!focusExecutionId && (
                <button
                  onClick={() => setShowSystemTools(!showSystemTools)}
                  className="ml-2 text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0"
                  title={t('systemStatusAndTools') || 'System Status & Tools'}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>
              )}
            </div>

            {/* Content Area */}
            {focusExecutionId ? (
              // Mode B (Playbook Perspective): Show Execution Chat
              <div className="flex-1 overflow-hidden">
                <ExecutionChatPanel
                  executionId={focusExecutionId}
                  workspaceId={workspaceId}
                  apiUrl={API_URL}
                  playbookMetadata={focusedPlaybookMetadata}
                />
              </div>
            ) : (
              // Mode A (Workspace Overview): Show Workspace Tools
              <div className="flex-1 flex flex-col overflow-hidden">
                {showSystemTools ? (
                  // Show System Tools Panel
                  <div className="flex-1 overflow-y-auto min-h-0">
                    <div className="p-3">
                      {systemStatus ? (
                        <IntegratedSystemStatusCard
                          systemStatus={systemStatus}
                          workspace={workspace || {}}
                          workspaceId={workspaceId}
                          onRefresh={loadSystemStatus}
                        />
                      ) : (
                        <div className="text-sm text-gray-500">Loading system status...</div>
                      )}
                    </div>
                  </div>
                ) : (
                  <>
                    {/* AI Team Collaboration Panel - Top */}
                    <div className="flex-1 border-b bg-blue-50/30 overflow-y-auto min-h-0">
                      <div className="p-3">
                        <PendingTasksPanel
                          workspaceId={workspaceId}
                          apiUrl={API_URL}
                          onViewArtifact={setSelectedArtifact}
                          workspace={workspace ? {
                            playbook_auto_execution_config: (workspace as any)?.playbook_auto_execution_config
                          } : undefined}
                        />
                      </div>
                    </div>
                    {/* Momo AI Workbench Section - Bottom (建議下一步) */}
                    <div className="flex-1 overflow-y-auto min-h-0">
                      <div className="p-4">
                        {workspace && workspace.mode === 'research' && (
                          <ResearchModePanel workspaceId={workspaceId} apiUrl={API_URL} />
                        )}
                        {workspace && workspace.mode === 'publishing' && (
                          <PublishingModePanel workspaceId={workspaceId} apiUrl={API_URL} />
                        )}
                        {workspace && workspace.mode === 'planning' && (
                          <PlanningModePanel workspaceId={workspaceId} apiUrl={API_URL} />
                        )}
                        {workspace && (!workspace.mode || (workspace.mode !== 'research' && workspace.mode !== 'publishing' && workspace.mode !== 'planning')) && (
                            <MindscapeAIWorkbench
                            workspaceId={workspaceId}
                            apiUrl={API_URL}
                            activeTab={rightSidebarTab}
                            onTabChange={(tab) => setRightSidebarTab(tab as any)}
                            refreshTrigger={workbenchRefreshTrigger}
                          />
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <OutcomeDetailModal
        artifact={selectedArtifact}
        isOpen={selectedArtifact !== null}
        onClose={() => setSelectedArtifact(null)}
        workspaceId={workspaceId}
        apiUrl={API_URL}
      />

      <ConfirmDialog
        isOpen={showDeleteDialog}
        onClose={() => setShowDeleteDialog(false)}
        onConfirm={async () => {
          if (!workspace) return;
          setIsDeleting(true);
          try {
            const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}`, {
              method: 'DELETE',
            });

            if (response.ok || response.status === 204) {
              router.push('/workspaces');
            } else {
              const errorData = await response.json().catch(() => ({}));
              alert(errorData.detail || t('workspaceDeleteFailed'));
              setIsDeleting(false);
              setShowDeleteDialog(false);
            }
          } catch (err) {
            console.error('Failed to delete workspace:', err);
            alert(t('workspaceDeleteFailed'));
            setIsDeleting(false);
            setShowDeleteDialog(false);
          }
        }}
        title={t('workspaceDelete')}
        message={workspace ? t('workspaceDeleteConfirm', { workspaceName: workspace.title }) : ''}
        confirmText={t('delete') || '刪除'}
        cancelText={t('cancel') || '取消'}
        confirmButtonClassName="bg-red-600 hover:bg-red-700"
      />
    </div>
  );
}


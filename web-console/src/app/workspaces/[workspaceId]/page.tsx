'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter, usePathname, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import WorkspaceChat from '../../../components/WorkspaceChat';
import MindscapeAIWorkbench from '../../../components/MindscapeAIWorkbench';
import ResearchModePanel from '../../../components/ResearchModePanel';
import PublishingModePanel from '../../../components/PublishingModePanel';
import PlanningModePanel from '../../../components/PlanningModePanel';
import IntegratedSystemStatusCard from '../../../components/IntegratedSystemStatusCard';
import WorkspaceScopePanel from '../components/WorkspaceScopePanel';
import StoragePathConfigModal from '@/components/StoragePathConfigModal';
import TimelinePanel from '../components/TimelinePanel';
import LeftSidebarTabs from './components/LeftSidebarTabs';
import ProjectCard from './components/ProjectCard';
import ProjectSubTabs from './components/ProjectSubTabs';
import OutcomesPanel, { Artifact } from './components/OutcomesPanel';
import ConversationsList from './components/ConversationsList';
import OutcomeDetailModal from '../components/OutcomeDetailModal';
import BackgroundTasksPanel from '../components/BackgroundTasksPanel';
import { PackPanel } from './components/PackPanel';
import { WorkspaceMode } from '../../../components/WorkspaceModeSelector';
import { t } from '@/lib/i18n';
import ConfirmDialog from '../../../components/ConfirmDialog';
import HelpIcon from '../../../components/HelpIcon';
import ExecutionInspector from '../components/ExecutionInspector';
import { ExecutionSidebar } from '@/components/execution';
import ExecutionChatPanel from '../components/ExecutionChatPanel';
import WorkspaceSettingsModal from './components/WorkspaceSettingsModal';
import RuntimeSettingsModal from './components/RuntimeSettingsModal';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import SandboxModal from '@/components/sandbox/SandboxModal';
import { getSandboxByProject } from '@/lib/sandbox-api';
import {
  TrainHeader,
  ExecutionModeSelector,
  ThinkingContext,
  ThinkingTimeline,
  ExecutionTree,
} from '../../../components/execution';
import AITeamPanel from '../../../components/execution/AITeamPanel';
import { useExecutionState } from '@/hooks/useExecutionState';
import { ArtifactsSummary } from '../../../components/workspace/ArtifactsSummary';
import { DecisionPanel } from '../../../components/workspace/DecisionPanel';
import { ResizablePanel } from '../../../components/ui/ResizablePanel';
import { Project } from '@/types/project';
import { ThreadBundlePanel } from '../../../components/workspace/ThreadBundlePanel';

import { getApiBaseUrl } from '../../../lib/api-url';

const API_URL = getApiBaseUrl();

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

type ExecutionMode = 'qa' | 'execution' | 'hybrid' | null;
type ExecutionPriority = 'low' | 'medium' | 'high' | null;

interface Workspace {
  id: string;
  title: string;
  description?: string;
  primary_project_id?: string;
  default_playbook_id?: string;
  default_locale?: string;
  mode?: WorkspaceMode;
  execution_mode?: ExecutionMode;
  expected_artifacts?: string[];
  execution_priority?: ExecutionPriority;
  data_sources?: DataSource | null;
  associated_intent?: AssociatedIntent | null;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  playbook_storage_config?: Record<string, { base_path?: string; artifacts_dir?: string }>;
}

// Internal component that uses Context data
function WorkspacePageContent({ workspaceId }: { workspaceId: string }) {
  const contextData = useWorkspaceData();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Use Context data instead of local state
  const workspace = contextData.workspace;
  const loading = contextData.isLoadingWorkspace;
  const error = contextData.error;
  const systemStatus = contextData.systemStatus;
  const [rightSidebarTab, setRightSidebarTab] = useState<'timeline' | 'workbench'>('timeline');
  const [leftSidebarTab, setLeftSidebarTab] = useState<'timeline' | 'outcomes' | 'pack'>('timeline');
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [updatingMode, setUpdatingMode] = useState(false);
  const [workbenchRefreshTrigger, setWorkbenchRefreshTrigger] = useState(0);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  // Execution pages now use dedicated routes: /workspaces/{workspaceId}/executions/{executionId}
  // These states are kept for backward compatibility but should not be used
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [focusExecutionId, setFocusExecutionId] = useState<string | null>(null);
  const [focusedExecution] = useState<any>(null);
  const [focusedPlaybookMetadata] = useState<any>(null);
  const [showSystemTools, setShowSystemTools] = useState(false);
  const [showRuntimeModal, setShowRuntimeModal] = useState(false);
  const [showDataSourcesModal, setShowDataSourcesModal] = useState(false);
  const [showFullSettings, setShowFullSettings] = useState(false);
  const [showSandboxModal, setShowSandboxModal] = useState(false);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const [sandboxProjectId, setSandboxProjectId] = useState<string | null>(null);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [isLoadingProject, setIsLoadingProject] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);  // 🆕 Current conversation thread
  const [isBundleOpen, setIsBundleOpen] = useState(false);  // 🆕 Bundle panel state

  // Execution state from hook (SSE-driven)
  const executionState = useExecutionState(workspaceId, API_URL);

  // Workspace name editing state
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState('');

  // Removed: fetchWithRetry and related refs - workspace loading is now handled by WorkspaceDataContext

  // Workspace loading is handled by WorkspaceDataContext
  // Use Context's methods for manual refresh
  const loadWorkspace = contextData.refreshWorkspace;

  // Listen for open-execution-inspector event - navigate to dedicated execution page
  useEffect(() => {
    const handleOpenExecutionInspector = (event: CustomEvent) => {
      const { executionId, workspaceId: eventWorkspaceId } = event.detail;
      // Only handle events for current workspace
      if (executionId && (!eventWorkspaceId || eventWorkspaceId === workspaceId)) {
        // Navigate to dedicated execution page
        const executionUrl = `/workspaces/${workspaceId}/executions/${executionId}`;
        console.log('[WorkspacePage] Navigating to execution page:', executionUrl);
        router.push(executionUrl);
      }
    };

    window.addEventListener('open-execution-inspector', handleOpenExecutionInspector as EventListener);
    return () => {
      window.removeEventListener('open-execution-inspector', handleOpenExecutionInspector as EventListener);
    };
  }, [workspaceId, router]);

  // Execution pages now use dedicated routes, so we don't need to load execution data here

  // Load projects list
  useEffect(() => {
    const loadProjects = async () => {
      setIsLoadingProjects(true);
      try {
        const url = new URL(`${API_URL}/api/v1/workspaces/${workspaceId}/projects`);
        url.searchParams.set('state', 'open');
        url.searchParams.set('limit', '20');
        if (selectedType) {
          url.searchParams.set('project_type', selectedType);
        }

        const response = await fetch(url.toString());
        if (response.ok) {
          const data = await response.json();
          setProjects(data.projects || []);

          // Set selected project
          // Set selected project
          const urlProjectId = searchParams?.get('project_id');
          if (urlProjectId) {
            setSelectedProjectId(urlProjectId);
          } else if (workspace?.primary_project_id) {
            setSelectedProjectId(workspace.primary_project_id);
          } else if (data.projects && data.projects.length > 0) {
            setSelectedProjectId(data.projects[0].id);
          }
        }
      } catch (err) {
        console.error('[WorkspacePage] Failed to load projects:', err);
        setProjects([]);
      } finally {
        setIsLoadingProjects(false);
      }
    };

    loadProjects();
  }, [workspaceId, workspace?.primary_project_id, selectedType]);

  // Load current project when workspace.primary_project_id or selectedProjectId changes
  useEffect(() => {
    const projectIdToLoad = selectedProjectId || workspace?.primary_project_id;

    console.log('[WorkspacePage] Workspace data:', {
      workspace_id: workspace?.id,
      primary_project_id: workspace?.primary_project_id,
      selected_project_id: selectedProjectId,
      project_id_to_load: projectIdToLoad,
      has_workspace: !!workspace
    });

    if (!projectIdToLoad) {
      console.log('[WorkspacePage] No project ID to load, setting currentProject to null');
      setCurrentProject(null);
      return;
    }

    const loadProject = async () => {
      setIsLoadingProject(true);
      try {
        console.log('[WorkspacePage] Loading project:', {
          workspaceId,
          project_id: projectIdToLoad
        });
        const response = await fetch(
          `${API_URL}/api/v1/workspaces/${workspaceId}/projects/${projectIdToLoad}`
        );
        if (response.ok) {
          const projectData = await response.json();
          console.log('[WorkspacePage] Project loaded:', {
            project_id: projectData.id,
            project_title: projectData.title,
            project_type: projectData.type,
            full_data: projectData
          });
          setCurrentProject(projectData);
        } else {
          // If project not found, try to get first active project from list
          if (projects && projects.length > 0) {
            setCurrentProject(projects[0]);
            setSelectedProjectId(projects[0].id);
          } else {
            setCurrentProject(null);
          }
        }
      } catch (err) {
        console.error('Failed to load project:', err);
        setCurrentProject(null);
      } finally {
        setIsLoadingProject(false);
      }
    };

    loadProject();
  }, [selectedProjectId, workspace?.primary_project_id, workspaceId, projects]);

  // Debug: Log currentProject changes
  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      console.log('[WorkspacePage] currentProject changed:', {
        currentProject_id: currentProject?.id,
        currentProject_title: currentProject?.title,
        has_currentProject: !!currentProject,
        workspace_primary_project_id: workspace?.primary_project_id,
        isLoadingProject
      });
    }
  }, [currentProject, workspace?.primary_project_id, isLoadingProject]);

  // Workspace loading is handled by WorkspaceDataContext - no need for useEffect here

  // Route by launch_status (state machine routing)
  // IMPORTANT: Only redirect pending workspaces to setup, don't force ready/active to home
  // This preserves the original "click to work" behavior
  useEffect(() => {
    if (!workspace || loading || !pathname) return;

    // Check if we're already on a specific route (home or work)
    // Only redirect if we're on the base /workspaces/:id route
    if (pathname !== `/workspaces/${workspaceId}`) {
      // Already on a specific route (home/work), don't auto-redirect
      return;
    }

    // Route based on launch_status
    const launchStatus = (workspace as any).launch_status || 'pending';
    console.log(`[WorkspacePage] Routing workspace ${workspaceId} with status: ${launchStatus}`);

    // ONLY redirect pending workspaces to setup
    // ready and active should stay on work page (preserve original behavior)
    if (launchStatus === 'pending') {
      // New workspace needs setup - redirect to home with setup drawer
      console.log(`[WorkspacePage] Redirecting pending workspace to /home?setup=true`);
      router.replace(`/workspaces/${workspaceId}/home?setup=true`);
    }
    // ready and active: stay on work page (no redirect)
    // Users can navigate to /home manually if they want to see Launchpad
  }, [workspace, loading, workspaceId, router, pathname]);


  const handleModeChange = async (mode: WorkspaceMode) => {
    if (!workspace) return;

    try {
      setUpdatingMode(true);
      // Use Context's updateWorkspace method
      await contextData.updateWorkspace({ mode: mode === null ? null : mode });
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
    const autoExecute = searchParams?.get('auto_execute_playbook') === 'true';
    const variantId = searchParams?.get('variant_id');

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
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-secondary dark:text-gray-400">{t('loadingWorkspace' as any)}</div>
        </div>
      </div>
    );
  }

  if (error || (!workspace && !loading)) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-center">
            <div className="text-red-500 dark:text-red-400 mb-4">{error || t('workspaceNotFound' as any)}</div>
            {error && error.includes('Rate limit') && (
              <button
                onClick={() => {
                  contextData.refreshWorkspace();
                }}
                className="px-4 py-2 bg-accent dark:bg-blue-700 text-white rounded hover:opacity-90 dark:hover:bg-blue-600"
              >
                {t('retryButton' as any)}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">

      <div className="flex flex-col h-[calc(100vh-48px)]">
        {/* Train Header - Progress Bar with Workspace Name */}
        {workspace && (
          <div className="relative">
            <TrainHeader
              workspaceName={workspace.title}
              steps={executionState.trainSteps}
              progress={executionState.overallProgress}
              isExecuting={executionState.isExecuting}
              workspaceId={workspaceId}
              onWorkspaceNameEdit={() => {
                setEditedName(workspace.title);
                setIsEditingName(true);
              }}
            />
            {/* Action Buttons - Right side of header */}
            <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2 z-20">
              {/* Mind Graph Button */}
              <button
                onClick={() => router.push(`/mindscape/canvas?workspaceId=${workspaceId}`)}
                className="px-3 py-1.5 text-sm bg-purple-100 dark:bg-purple-900/30 rounded-lg
                           hover:bg-purple-200 dark:hover:bg-purple-800/40 transition-colors
                           flex items-center gap-1.5 text-purple-700 dark:text-purple-300"
                title="心智執行圖"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <span>Graph</span>
              </button>
              {/* Bundle Button */}
              {selectedThreadId && (
                <button
                  onClick={() => setIsBundleOpen(true)}
                  className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg
                             hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors
                             flex items-center gap-1.5"
                  title="開啟成果包"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                  <span>Bundle</span>
                </button>
              )}
            </div>
          </div>
        )}

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar - Tab Panel and Workspace Scope Panel */}
          <div className="w-80 border-r dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
            {/* Tab Panel Section - Top */}
            <div className="flex-1 overflow-hidden min-h-0">
              <LeftSidebarTabs
                activeTab={leftSidebarTab}
                onTabChange={setLeftSidebarTab}
                timelineContent={
                  <div className="flex flex-col h-full">
                    {projects.length > 0 && (
                      <ProjectSubTabs
                        projects={projects}
                        selectedType={selectedType}
                        selectedProjectId={selectedProjectId}
                        onTypeChange={setSelectedType}
                        onProjectSelect={(project) => {
                          setSelectedProjectId(project.id);
                          setCurrentProject(project);
                        }}
                      />
                    )}

                    {/* Project Card */}
                    <div className="flex-shrink-0 border-b dark:border-gray-700 p-3">
                      {isLoadingProject ? (
                        <div className="text-xs text-secondary dark:text-gray-400">
                          載入中...
                        </div>
                      ) : currentProject ? (
                        <ProjectCard
                          project={currentProject}
                          workspaceId={workspaceId}
                          apiUrl={API_URL}
                          defaultExpanded={true}
                          onOpenExecution={(executionId) => {
                            // Navigate to dedicated execution page
                            const executionUrl = `/workspaces/${workspaceId}/executions/${executionId}`;
                            console.log('[WorkspacePage] ProjectCard onOpenExecution, navigating to:', executionUrl);
                            router.push(executionUrl);
                          }}
                        />
                      ) : (
                        <div className="px-3 py-2">
                          <div className="project-placeholder text-center py-8">
                            <div className="text-2xl mb-2">📁</div>
                            <div className="text-sm font-medium text-primary dark:text-gray-300 mb-1">
                              尚無進行中的專案
                            </div>
                            <div className="text-xs text-secondary dark:text-gray-400">
                              開始對話後，系統會自動建立專案
                            </div>
                            {/* Debug info */}
                            {process.env.NODE_ENV === 'development' && (
                              <div className="mt-4 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-xs text-left">
                                <div><strong>🔍 Debug Info:</strong></div>
                                <div>workspace.primary_project_id: {workspace?.primary_project_id || '❌ null'}</div>
                                <div>currentProject exists: {currentProject ? '✅ YES' : '❌ NO'}</div>
                                {currentProject && (
                                  <>
                                    <div>currentProject.id: {(currentProject as any).id || '❌ MISSING!'}</div>
                                    <div>currentProject.title: {(currentProject as any).title}</div>
                                    <div>currentProject.type: {(currentProject as any).type}</div>
                                  </>
                                )}
                                <div>isLoadingProject: {isLoadingProject ? '⏳ true' : '✅ false'}</div>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* ExecutionSidebar 已移除 - 左侧边栏主要显示 project card */}
                  </div>
                }
                outcomesContent={
                  <TimelinePanel
                    workspaceId={workspaceId}
                    apiUrl={API_URL}
                    isInSettingsPage={false}
                    showArchivedOnly={true}
                  />
                }
                packContent={
                  <PackPanel
                    workspaceId={workspaceId}
                    apiUrl={API_URL}
                    storyThreadId={workspace?.primary_project_id ? undefined : undefined}
                  />
                }
              />
            </div>

            {/* Workspace Settings - Collapsible at bottom */}
            {workspace && (
              <div className="border-t dark:border-gray-700 bg-surface-secondary dark:bg-orange-900/10 mt-auto">
                {/* Settings Entry - Collapsible in left sidebar */}
                <div className="border-t dark:border-gray-700">
                  <div
                    className="px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
                    onClick={() => setShowSystemTools(!showSystemTools)}
                  >
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      <div>
                        <div className="text-xs font-medium text-primary dark:text-gray-300">工作區設定</div>
                        <div className="text-[10px] text-tertiary">模式 · 產物 · 偏好 · 資料來源</div>
                      </div>
                    </div>
                    <span className="text-tertiary text-xs">{showSystemTools ? '▲' : '▼'}</span>
                  </div>

                  {/* Collapsible Settings Panel */}
                  <div
                    className={`border-t dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out ${showSystemTools ? 'max-h-[400px] opacity-100' : 'max-h-0 opacity-0'
                      }`}
                  >
                    {showSystemTools && (
                      <div className="overflow-y-auto max-h-[400px]">
                        {/* Settings Tab Buttons */}
                        <div className="flex border-b dark:border-gray-700">
                          <button
                            onClick={() => setShowDataSourcesModal(true)}
                            className="flex-1 px-3 py-2 text-xs font-medium text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors border-r dark:border-gray-700"
                          >
                            📁 資料來源
                          </button>
                          <button
                            onClick={() => setShowRuntimeModal(true)}
                            className="flex-1 px-3 py-2 text-xs font-medium text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
                          >
                            ☁️ 雲端 Runtime
                          </button>
                        </div>

                        {/* System Status Section */}
                        <div className="p-3">
                          {systemStatus ? (
                            <IntegratedSystemStatusCard
                              systemStatus={systemStatus}
                              workspace={workspace || {}}
                              workspaceId={workspaceId}
                              onRefresh={() => contextData.refreshAll()}
                            />
                          ) : (
                            <div className="text-sm text-secondary dark:text-gray-400">Loading system status...</div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Settings Modals */}
            {workspace && (
              <>
                <StoragePathConfigModal
                  isOpen={showDataSourcesModal}
                  onClose={() => setShowDataSourcesModal(false)}
                  workspace={workspace as any}
                  workspaceId={workspaceId}
                  apiUrl={API_URL}
                  toolConnections={systemStatus?.tools}
                  onSuccess={() => {
                    window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                  }}
                />
                <RuntimeSettingsModal
                  isOpen={showRuntimeModal}
                  onClose={() => setShowRuntimeModal(false)}
                  workspaceId={workspaceId}
                />
              </>
            )}
          </div>

          {/* Main Area - Workspace Chat */}
          <div className="flex-1 flex flex-col" style={{ minWidth: 0, overflow: 'hidden' }}>
            {selectedExecutionId ? (
              <ExecutionInspector
                executionId={selectedExecutionId}
                workspaceId={workspaceId}
                apiUrl={API_URL}
                onClose={() => {
                  setSelectedExecutionId(null);
                  setFocusExecutionId(null); // Clear focus mode
                  // Update URL to remove execution query parameter
                  const newUrl = `/workspaces/${workspaceId}`;
                  router.push(newUrl);
                  // Dispatch event to ensure all components are notified
                  window.dispatchEvent(new CustomEvent('clear-execution-focus'));
                }}
              />
            ) : (
              <WorkspaceChat
                workspaceId={workspaceId}
                apiUrl={API_URL}
                projectId={currentProject?.id}  // Pass current project ID
                threadId={selectedThreadId}  // 🆕 Pass current thread ID
                onFileAnalyzed={() => {
                  // Refresh workbench when file is analyzed
                  setWorkbenchRefreshTrigger(prev => prev + 1);
                }}
                executionMode={workspace?.execution_mode || 'hybrid'}
                expectedArtifacts={workspace?.expected_artifacts}
              />
            )}
          </div>

          {/* Right Sidebar - Execution Chat (when focused) or Workspace Tools (default) */}
          <div className="w-80 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
            {/* Header - Title with AI Team Mode Selector */}
            <div className="flex items-center justify-between border-b dark:border-gray-700 bg-surface dark:bg-gray-800 px-3 py-1.5">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <h3 className="text-xs font-bold bg-gradient-to-r from-accent dark:from-blue-600 to-gray-600 text-white px-2 py-0.5 rounded-lg shadow-md border border-accent dark:border-blue-700 flex-shrink-0">
                  {t('mindscapeAIWorkbench' as any)}
                </h3>
                <div className="h-3 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>
                {focusExecutionId ? (
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <h3 className="text-xs font-semibold text-primary dark:text-gray-100">
                      {focusedPlaybookMetadata?.title || focusedExecution?.playbook_code || t('playbookConversation' as any)}
                    </h3>
                  </div>
                ) : (
                  /* AI Team + Execution Mode integrated */
                  workspace && (
                    <ExecutionModeSelector
                      key={`exec-mode-${workspace.id}-${workspace.execution_mode || 'hybrid'}-${workspace.execution_priority || 'medium'}`}
                      mode={(workspace.execution_mode as 'qa' | 'execution' | 'hybrid') || 'hybrid'}
                      priority={(workspace.execution_priority as 'low' | 'medium' | 'high') || 'medium'}
                      onChange={async (update) => {
                        try {
                          const updated = await contextData.updateWorkspace({
                            execution_mode: update.mode,
                            execution_priority: update.priority,
                          });
                          // WorkspaceDataContext 會自動更新 workspace 狀態
                          // key prop 確保組件在 workspace 更新時重新渲染
                        } catch (err) {
                          console.error('Failed to update execution mode:', err);
                        }
                      }}
                    />
                  )
                )}
              </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-hidden flex flex-col">
              <ResizablePanel
                defaultTopHeight={focusExecutionId ? 30 : 40}
                minTopHeight={20}
                minBottomHeight={20}
                top={
                  <div className="h-full overflow-hidden border-b dark:border-gray-700">
                    <ConversationsList
                      workspaceId={workspaceId}
                      apiUrl={API_URL}
                      selectedThreadId={selectedThreadId}
                      onThreadSelect={setSelectedThreadId}
                    />
                  </div>
                }
                bottom={
                  focusExecutionId ? (
                    // Mode B (Playbook Perspective): Show Execution Chat
                    <div className="h-full overflow-hidden">
                      <ExecutionChatPanel
                        key={focusExecutionId}
                        executionId={focusExecutionId}
                        workspaceId={workspaceId}
                        apiUrl={API_URL}
                        playbookMetadata={focusedPlaybookMetadata}
                      />
                    </div>
                  ) : (
                    // Mode A (Workspace Perspective): Show Workspace Tools
                    <div className="flex-1 flex flex-col overflow-hidden">
                      <ResizablePanel
                        defaultTopHeight={50}
                        minTopHeight={20}
                        minBottomHeight={20}
                        top={
                          <section className="sidebar-section ai-team-section h-full overflow-hidden flex flex-col">
                            <div className="flex-1 overflow-y-auto min-h-0 bg-accent-10 dark:bg-blue-900/10">
                              <div className="p-3">
                                {(workspace?.execution_mode === 'hybrid' || workspace?.execution_mode === 'execution') && (
                                  <>
                                    {executionState.isExecuting && (
                                      <ThinkingContext
                                        summary={executionState.thinkingSummary}
                                        pipelineStage={executionState.pipelineStage}
                                        isLoading={executionState.isExecuting && !executionState.pipelineStage && !executionState.thinkingSummary}
                                      />
                                    )}

                                    {(() => {
                                      // Show AI Team if there are members, regardless of execution state
                                      // AI Team should be visible even when not actively executing (shows recent/relevant team members)
                                      const shouldShow = executionState.aiTeamMembers.length > 0;
                                      console.log('[WorkspacePage] AITeamPanel render check:', {
                                        aiTeamMembersCount: executionState.aiTeamMembers.length,
                                        pipelineStage: executionState.pipelineStage?.stage,
                                        isExecuting: executionState.isExecuting,
                                        shouldShow,
                                        members: executionState.aiTeamMembers,
                                        executionMode: workspace?.execution_mode
                                      });
                                      if (shouldShow) {
                                        console.log('[WorkspacePage] Rendering AITeamPanel with members:', executionState.aiTeamMembers);
                                      } else {
                                        console.log('[WorkspacePage] Not rendering AITeamPanel - no members');
                                      }
                                      return shouldShow ? (
                                        <div className="mt-3">
                                          <AITeamPanel
                                            members={executionState.aiTeamMembers}
                                            isLoading={executionState.isExecuting}
                                          />
                                        </div>
                                      ) : null;
                                    })()}
                                  </>
                                )}

                                <ArtifactsSummary
                                  count={executionState.producedArtifacts.length}
                                  onViewAll={() => {
                                    // 跳轉到左側「成果」Tab
                                    setLeftSidebarTab('outcomes');
                                  }}
                                />
                              </div>
                            </div>
                          </section>
                        }
                        bottom={
                          <ResizablePanel
                            defaultTopHeight={50}
                            minTopHeight={20}
                            minBottomHeight={20}
                            top={
                              <section className="sidebar-section decision-section h-full overflow-hidden flex flex-col">
                                <DecisionPanel
                                  workspaceId={workspaceId}
                                  apiUrl={API_URL}
                                  onViewArtifact={setSelectedArtifact}
                                  onSwitchToOutcomes={() => setLeftSidebarTab('outcomes')}
                                  workspace={workspace ? {
                                    playbook_auto_execution_config: (workspace as any)?.playbook_auto_execution_config,
                                    owner_user_id: (workspace as any)?.owner_user_id
                                  } : undefined}
                                />
                              </section>
                            }
                            bottom={
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
                            }
                          />
                        }
                      />
                    </div>
                  )
                }
              />
            </div>
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
              alert(errorData.detail || t('workspaceDeleteFailed' as any));
              setIsDeleting(false);
              setShowDeleteDialog(false);
            }
          } catch (err) {
            console.error('Failed to delete workspace:', err);
            alert(t('workspaceDeleteFailed' as any));
            setIsDeleting(false);
            setShowDeleteDialog(false);
          }
        }}
        title={t('workspaceDelete' as any)}
        message={workspace ? t('workspaceDeleteConfirm', { workspaceName: workspace.title }) : ''}
        confirmText={t('delete' as any) || '刪除'}
        cancelText={t('cancel' as any) || '取消'}
        confirmButtonClassName="bg-red-600 hover:bg-red-700"
      />

      {/* Sandbox Modal */}
      {showSandboxModal && sandboxId && (
        <SandboxModal
          isOpen={showSandboxModal}
          onClose={() => setShowSandboxModal(false)}
          workspaceId={workspaceId}
          sandboxId={sandboxId}
          projectId={sandboxProjectId || undefined}
          executionId={focusedExecution?.execution_id || selectedExecutionId || undefined}
        />
      )}

      <WorkspaceSettingsModal
        isOpen={showFullSettings}
        onClose={() => setShowFullSettings(false)}
        workspace={workspace ? {
          ...workspace,
          execution_mode: workspace.execution_mode ?? undefined,
          execution_priority: workspace.execution_priority ?? undefined
        } : null}
        workspaceId={workspaceId}
        apiUrl={API_URL}
        onUpdate={() => {
          contextData.refreshWorkspace();
        }}
      />

      {/* Thread Bundle Panel */}
      <ThreadBundlePanel
        threadId={selectedThreadId}
        workspaceId={workspaceId}
        isOpen={isBundleOpen}
        onClose={() => setIsBundleOpen(false)}
        apiUrl={API_URL}
      />
    </div>
  );
}

// External component - Context is now provided by layout.tsx
export default function WorkspacePage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;

  if (!workspaceId) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-secondary dark:text-gray-400">{t('workspaceNotFound' as any)}</div>
        </div>
      </div>
    );
  }

  return <WorkspacePageContent workspaceId={workspaceId} />;
}


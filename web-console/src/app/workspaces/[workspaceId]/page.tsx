'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import WorkspaceChat from '../../../components/WorkspaceChat';
import MindscapeAIWorkbench from '../../../components/MindscapeAIWorkbench';
import ResearchModePanel from '../../../components/ResearchModePanel';
import PublishingModePanel from '../../../components/PublishingModePanel';
import PlanningModePanel from '../../../components/PlanningModePanel';
import IntegratedSystemStatusCard from '../../../components/IntegratedSystemStatusCard';
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
import WorkspaceSettingsModal from './components/WorkspaceSettingsModal';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import SandboxModal from '@/components/sandbox/SandboxModal';
import { getSandboxByProject } from '@/lib/sandbox-api';
import {
  TrainHeader,
  ExecutionModeSelector,
  ThinkingContext,
  ArtifactsList,
  ThinkingTimeline,
  ExecutionTree,
} from '../../../components/execution';
import AITeamPanel from '../../../components/execution/AITeamPanel';
import { useExecutionState } from '@/hooks/useExecutionState';

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

  // Use Context data instead of local state
  const workspace = contextData.workspace;
  const loading = contextData.isLoadingWorkspace;
  const error = contextData.error;
  const systemStatus = contextData.systemStatus;
  const [rightSidebarTab, setRightSidebarTab] = useState<'timeline' | 'workbench'>('timeline');
  const [leftSidebarTab, setLeftSidebarTab] = useState<'timeline' | 'outcomes' | 'background'>('timeline');
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [updatingMode, setUpdatingMode] = useState(false);
  const [workbenchRefreshTrigger, setWorkbenchRefreshTrigger] = useState(0);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [focusExecutionId, setFocusExecutionId] = useState<string | null>(null);
  const [focusedExecution, setFocusedExecution] = useState<any>(null);
  const [focusedPlaybookMetadata, setFocusedPlaybookMetadata] = useState<any>(null);
  const [showSystemTools, setShowSystemTools] = useState(false);
  const [showFullSettings, setShowFullSettings] = useState(false);
  const [showSandboxModal, setShowSandboxModal] = useState(false);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const [sandboxProjectId, setSandboxProjectId] = useState<string | null>(null);

  // Execution state from hook (SSE-driven)
  const executionState = useExecutionState(workspaceId, API_URL);

  // Workspace name editing state
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState('');

  // Removed: fetchWithRetry and related refs - workspace loading is now handled by WorkspaceDataContext

  // Workspace loading is handled by WorkspaceDataContext
  // Use Context's methods for manual refresh
  const loadWorkspace = contextData.refreshWorkspace;

  // Listen for open-execution-inspector event
  useEffect(() => {
    const handleOpenExecutionInspector = (event: CustomEvent) => {
      const { executionId, workspaceId: eventWorkspaceId } = event.detail;
      // Only handle events for current workspace
      if (executionId && (!eventWorkspaceId || eventWorkspaceId === workspaceId)) {
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
  }, [workspaceId]);

  // Load focused execution and playbook metadata when focusExecutionId changes
  useEffect(() => {
    if (!focusExecutionId || !workspaceId) {
      setFocusedExecution(null);
      setFocusedPlaybookMetadata(null);
      return;
    }

    const loadFocusedExecution = async () => {
      try {
        // Load execution and check for project_id
        const execResponse = await fetch(
          `${API_URL}/api/v1/workspaces/${workspaceId}/executions/${focusExecutionId}`
        );
        if (execResponse.ok) {
          const execData = await execResponse.json();
          setFocusedExecution(execData);

          // Check for project_id and load sandbox
          const projectId = execData.project_id || execData.execution_context?.project_id;
          if (projectId) {
            setSandboxProjectId(projectId);
            try {
              const sandbox = await getSandboxByProject(workspaceId, projectId);
              if (sandbox) {
                setSandboxId(sandbox.sandbox_id);
              } else {
                setSandboxId(null);
              }
            } catch (err) {
              console.error('Failed to load sandbox:', err);
              setSandboxId(null);
            }
          } else {
            setSandboxProjectId(null);
            setSandboxId(null);
          }

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

  // Workspace loading is handled by WorkspaceDataContext - no need for useEffect here


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
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-gray-500 dark:text-gray-400">{t('loadingWorkspace')}</div>
        </div>
      </div>
    );
  }

  if (error || (!workspace && !loading)) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-center">
            <div className="text-red-500 dark:text-red-400 mb-4">{error || t('workspaceNotFound')}</div>
            {error && error.includes('Rate limit') && (
              <button
                onClick={() => {
                  contextData.refreshWorkspace();
                }}
                className="px-4 py-2 bg-blue-500 dark:bg-blue-700 text-white rounded hover:bg-blue-600 dark:hover:bg-blue-600"
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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">

      <div className="flex flex-col h-[calc(100vh-48px)]">
        {/* Train Header - Progress Bar with Workspace Name */}
        {workspace && (
          <TrainHeader
            workspaceName={workspace.title}
            steps={executionState.trainSteps}
            progress={executionState.overallProgress}
            isExecuting={executionState.isExecuting}
            onWorkspaceNameEdit={() => {
              setEditedName(workspace.title);
              setIsEditingName(true);
            }}
          />
        )}

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar - Tab Panel and Workspace Scope Panel */}
          <div className="w-80 border-r dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col">
            {/* Tab Panel Section - Top */}
            <div className="flex-1 overflow-hidden min-h-0">
              <LeftSidebarTabs
                activeTab={leftSidebarTab}
                onTabChange={setLeftSidebarTab}
                timelineContent={
                  <div className="flex flex-col h-full">
                    {/* Timeline Panel - Main content (has its own scroll) */}
                    <div className="flex-1 min-h-0">
                      <TimelinePanel
                        workspaceId={workspaceId}
                        apiUrl={API_URL}
                        isInSettingsPage={false}
                        focusExecutionId={focusExecutionId}
                        onClearFocus={() => {
                          setFocusExecutionId(null);
                          setSelectedExecutionId(null);
                          // Also dispatch event to ensure all components are notified
                          window.dispatchEvent(new CustomEvent('clear-execution-focus'));
                        }}
                        onArtifactClick={setSelectedArtifact}
                      />
                    </div>

                    {/* Thinking Timeline - Recent execution history (below TimelinePanel) */}
                    {executionState.thinkingTimeline.length > 0 && (
                      <div className="border-t dark:border-gray-700 flex-shrink-0">
                        <ThinkingTimeline
                          entries={executionState.thinkingTimeline}
                          maxEntries={3}
                          isCollapsed={false}
                        />
                      </div>
                    )}
                  </div>
                }
                outcomesContent={
                  <TimelinePanel
                    workspaceId={workspaceId}
                    apiUrl={API_URL}
                    isInSettingsPage={false}
                    focusExecutionId={focusExecutionId}
                    onClearFocus={() => {
                      setFocusExecutionId(null);
                      setSelectedExecutionId(null);
                      window.dispatchEvent(new CustomEvent('clear-execution-focus'));
                    }}
                    showArchivedOnly={true}
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

            {/* Workspace Settings - Collapsible at bottom */}
            {workspace && (
              <div className="border-t dark:border-gray-700 bg-orange-50/30 dark:bg-orange-900/10 mt-auto">
                {/* Settings Entry - Collapsible in left sidebar */}
                <div className="border-t dark:border-gray-700">
                  <div
                    className="px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                    onClick={() => setShowSystemTools(!showSystemTools)}
                  >
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      <div>
                        <div className="text-xs font-medium text-gray-700 dark:text-gray-300">工作區設定</div>
                        <div className="text-[10px] text-gray-400">模式 · 產物 · 偏好 · 資料來源</div>
                      </div>
                    </div>
                    <span className="text-gray-400 text-xs">{showSystemTools ? '▲' : '▼'}</span>
                  </div>

                  {/* Collapsible Settings Panel */}
                  <div
                    className={`border-t dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out ${
                      showSystemTools ? 'max-h-[400px] opacity-100' : 'max-h-0 opacity-0'
                    }`}
                  >
                    {showSystemTools && (
                      <div className="overflow-y-auto max-h-[400px]">
                        {/* Quick Settings View */}
                        <>
                          {/* Data Sources Section */}
                          <div className="p-3 border-b dark:border-gray-700">
                            <WorkspaceScopePanel
                              dataSources={workspace.data_sources}
                              workspaceId={workspaceId}
                              apiUrl={API_URL}
                              workspace={workspace}
                            />
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
                              <div className="text-sm text-gray-500 dark:text-gray-400">Loading system status...</div>
                            )}
                          </div>
                        </>
                      </div>
                    )}
                  </div>
                </div>
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
                executionMode={workspace?.execution_mode || 'qa'}
                expectedArtifacts={workspace?.expected_artifacts}
              />
            )}
          </div>

          {/* Right Sidebar - Execution Chat (when focused) or Workspace Tools (default) */}
          <div className="w-80 border-l dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col">
            {/* Header - Title with AI Team Mode Selector */}
            <div className="flex items-center justify-between border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-1.5">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <h3 className="text-xs font-bold bg-gradient-to-r from-blue-500 to-gray-600 text-white px-2 py-0.5 rounded-lg shadow-md border border-blue-300 dark:border-blue-700 flex-shrink-0">
                  {t('mindscapeAIWorkbench')}
                </h3>
                <div className="h-3 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>
                {focusExecutionId ? (
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <h3 className="text-xs font-semibold text-gray-900 dark:text-gray-100">
                      {focusedPlaybookMetadata?.title || focusedExecution?.playbook_code || t('playbookConversation')}
                    </h3>
                  </div>
                ) : (
                  /* AI Team + Execution Mode integrated */
                  workspace && (
                    <ExecutionModeSelector
                      mode={(workspace.execution_mode as 'qa' | 'execution' | 'hybrid') || 'qa'}
                      priority={(workspace.execution_priority as 'low' | 'medium' | 'high') || 'medium'}
                      onChange={async (update) => {
                        try {
                          await contextData.updateWorkspace({
                            execution_mode: update.mode,
                            execution_priority: update.priority,
                          });
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
            {focusExecutionId ? (
              // Mode B (Playbook Perspective): Show Execution Chat
              <div className="flex-1 overflow-hidden">
                <ExecutionChatPanel
                  key={focusExecutionId}
                  executionId={focusExecutionId}
                  workspaceId={workspaceId}
                  apiUrl={API_URL}
                  playbookMetadata={focusedPlaybookMetadata}
                />
              </div>
            ) : (
              // Mode A (Workspace Overview): Show Workspace Tools
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* AI Team Collaboration Panel - Top */}
                <div className="flex-1 border-b dark:border-gray-700 bg-blue-50/30 dark:bg-blue-900/10 overflow-y-auto min-h-0">
                  <div className="p-3">
                    {/* Thinking Context - AI's thought process */}
                    {(workspace?.execution_mode === 'hybrid' || workspace?.execution_mode === 'execution') &&
                     executionState.isExecuting && (
                      <>
                        <ThinkingContext
                          summary={executionState.thinkingSummary}
                          pipelineStage={executionState.pipelineStage}
                          isLoading={executionState.isExecuting && !executionState.pipelineStage && !executionState.thinkingSummary}
                        />

                        {/* AI Team Panel - Only show if there are members and not in no_action_needed/no_playbook_found stage */}
                        {executionState.aiTeamMembers.length > 0 &&
                         executionState.pipelineStage?.stage !== 'no_action_needed' &&
                         executionState.pipelineStage?.stage !== 'no_playbook_found' && (
                          <div className="mt-3">
                            <AITeamPanel
                              members={executionState.aiTeamMembers}
                              isLoading={executionState.isExecuting}
                            />
                          </div>
                        )}
                      </>
                    )}

                        {/* Produced Artifacts */}
                        <ArtifactsList
                          artifacts={executionState.producedArtifacts}
                          onView={(artifact: any) => {
                            setSelectedArtifact(artifact);
                          }}
                          onViewSandbox={(sandboxId: string) => {
                            setSandboxId(sandboxId);
                            setShowSandboxModal(true);
                          }}
                          sandboxId={sandboxId || undefined}
                        />

                        {/* Pending Tasks Panel */}
                        <PendingTasksPanel
                          workspaceId={workspaceId}
                          apiUrl={API_URL}
                          onViewArtifact={setSelectedArtifact}
                          onSwitchToOutcomes={() => setLeftSidebarTab('outcomes')}
                          workspace={workspace ? {
                            playbook_auto_execution_config: (workspace as any)?.playbook_auto_execution_config
                          } : undefined}
                        />
                      </div>
                    </div>
                    {/* AI Workbench Section - Bottom */}
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

      {/* Workspace Settings Modal */}
      <WorkspaceSettingsModal
        isOpen={showFullSettings}
        onClose={() => setShowFullSettings(false)}
        workspace={workspace}
        workspaceId={workspaceId}
        apiUrl={API_URL}
        onUpdate={() => {
          contextData.refreshWorkspace();
        }}
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
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-gray-500 dark:text-gray-400">{t('workspaceNotFound')}</div>
        </div>
      </div>
    );
  }

  return <WorkspacePageContent workspaceId={workspaceId} />;
}


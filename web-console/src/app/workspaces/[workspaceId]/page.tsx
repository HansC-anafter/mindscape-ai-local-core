'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import WorkspaceChat from '../../../components/WorkspaceChat';
import ExecutionInspector from '../components/ExecutionInspector';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import { useExecutionState } from '@/hooks/useExecutionState';
import { useWorkspaceProjects } from '@/hooks/useWorkspaceProjects';
import { useWorkspaceAutoActions } from '@/hooks/useWorkspaceAutoActions';
import { Artifact } from './components/OutcomesPanel';
import { WorkspaceMode } from '../../../components/WorkspaceModeSelector';
import { t } from '@/lib/i18n';
import { getApiBaseUrl } from '../../../lib/api-url';

// Extracted sub-components
import WorkspaceHeaderBar from './components/WorkspaceHeaderBar';
import WorkspaceLeftSidebar from './components/WorkspaceLeftSidebar';
import WorkspaceRightSidebar from './components/WorkspaceRightSidebar';
import WorkspaceModals from './components/WorkspaceModals';

import type { Workspace } from './workspace-page.types';

const API_URL = getApiBaseUrl();

// Internal component that uses Context data
function WorkspacePageContent({ workspaceId }: { workspaceId: string }) {
  const contextData = useWorkspaceData();
  const router = useRouter();

  // Use Context data instead of local state
  const workspace = contextData.workspace as Workspace | null;
  const loading = contextData.isLoadingWorkspace;
  const error = contextData.error;
  const systemStatus = contextData.systemStatus;

  // Execution state from hook (SSE-driven)
  const executionState = useExecutionState(workspaceId, API_URL);

  // Project loading from extracted hook
  const projectState = useWorkspaceProjects(workspaceId, workspace);

  // URL-parameter-driven auto-actions (routing, auto-execute, meeting)
  useWorkspaceAutoActions(workspaceId, workspace, loading);

  // UI state - sidebar tabs
  const [rightSidebarTab, setRightSidebarTab] = useState<'timeline' | 'workbench'>('timeline');
  const [leftSidebarTab, setLeftSidebarTab] = useState<'timeline' | 'outcomes' | 'pack'>('timeline');

  // UI state - modals and dialogs
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showSystemTools, setShowSystemTools] = useState(false);
  const [showRuntimeModal, setShowRuntimeModal] = useState(false);
  const [showInstructionModal, setShowInstructionModal] = useState(false);
  const [showDataSourcesModal, setShowDataSourcesModal] = useState(false);
  const [showFullSettings, setShowFullSettings] = useState(false);
  const [showSandboxModal, setShowSandboxModal] = useState(false);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const [sandboxProjectId, setSandboxProjectId] = useState<string | null>(null);

  // UI state - workbench
  const [updatingMode, setUpdatingMode] = useState(false);
  const [workbenchRefreshTrigger, setWorkbenchRefreshTrigger] = useState(0);

  // Execution pages now use dedicated routes: /workspaces/{workspaceId}/executions/{executionId}
  // These states are kept for backward compatibility but should not be used
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [focusExecutionId, setFocusExecutionId] = useState<string | null>(null);
  const [focusedExecution] = useState<any>(null);
  const [focusedPlaybookMetadata] = useState<any>(null);

  // Thread state
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [isBundleOpen, setIsBundleOpen] = useState(false);

  // Workspace name editing state
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState('');

  // Workspace loading is handled by WorkspaceDataContext
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
          <WorkspaceHeaderBar
            workspace={workspace}
            workspaceId={workspaceId}
            apiUrl={API_URL}
            executionState={executionState}
            selectedThreadId={selectedThreadId}
            onWorkspaceNameEdit={() => {
              setEditedName(workspace.title);
              setIsEditingName(true);
            }}
            onBundleOpen={() => setIsBundleOpen(true)}
          />
        )}

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar - Tab Panel and Workspace Scope Panel */}
          <WorkspaceLeftSidebar
            workspace={workspace}
            workspaceId={workspaceId}
            apiUrl={API_URL}
            systemStatus={systemStatus}
            projects={projectState.projects}
            currentProject={projectState.currentProject}
            selectedProjectId={projectState.selectedProjectId}
            selectedType={projectState.selectedType}
            isLoadingProject={projectState.isLoadingProject}
            leftSidebarTab={leftSidebarTab}
            setLeftSidebarTab={setLeftSidebarTab}
            setSelectedType={projectState.setSelectedType}
            onProjectSelect={(project) => {
              projectState.setSelectedProjectId(project.id);
              projectState.setCurrentProject(project);
            }}
            showSystemTools={showSystemTools}
            setShowSystemTools={setShowSystemTools}
            showDataSourcesModal={showDataSourcesModal}
            setShowDataSourcesModal={setShowDataSourcesModal}
            showRuntimeModal={showRuntimeModal}
            setShowRuntimeModal={setShowRuntimeModal}
            showInstructionModal={showInstructionModal}
            setShowInstructionModal={setShowInstructionModal}
            onRefreshAll={() => contextData.refreshAll()}
          />

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
                projectId={projectState.currentProject?.id}
                threadId={selectedThreadId}
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
          <WorkspaceRightSidebar
            workspace={workspace}
            workspaceId={workspaceId}
            apiUrl={API_URL}
            executionState={executionState}
            focusExecutionId={focusExecutionId}
            focusedExecution={focusedExecution}
            focusedPlaybookMetadata={focusedPlaybookMetadata}
            selectedThreadId={selectedThreadId}
            rightSidebarTab={rightSidebarTab}
            workbenchRefreshTrigger={workbenchRefreshTrigger}
            setRightSidebarTab={setRightSidebarTab}
            setSelectedArtifact={setSelectedArtifact}
            setLeftSidebarTab={setLeftSidebarTab}
            setSelectedThreadId={setSelectedThreadId}
            contextData={contextData}
          />
        </div>
      </div>

      {/* Modals and Dialogs */}
      <WorkspaceModals
        workspace={workspace}
        workspaceId={workspaceId}
        apiUrl={API_URL}
        selectedArtifact={selectedArtifact}
        setSelectedArtifact={setSelectedArtifact}
        showDeleteDialog={showDeleteDialog}
        setShowDeleteDialog={setShowDeleteDialog}
        isDeleting={isDeleting}
        setIsDeleting={setIsDeleting}
        showSandboxModal={showSandboxModal}
        setShowSandboxModal={setShowSandboxModal}
        sandboxId={sandboxId}
        sandboxProjectId={sandboxProjectId}
        focusedExecution={focusedExecution}
        selectedExecutionId={selectedExecutionId}
        showFullSettings={showFullSettings}
        setShowFullSettings={setShowFullSettings}
        onSettingsUpdate={() => {
          contextData.refreshWorkspace();
        }}
        selectedThreadId={selectedThreadId}
        isBundleOpen={isBundleOpen}
        setIsBundleOpen={setIsBundleOpen}
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

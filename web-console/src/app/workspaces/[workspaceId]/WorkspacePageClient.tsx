'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import { useExecutionState } from '@/hooks/useExecutionState';
import { useWorkspaceProjects } from '@/hooks/useWorkspaceProjects';
import { useWorkspaceAutoActions } from '@/hooks/useWorkspaceAutoActions';
import type { Artifact } from './components/OutcomesPanel';
import { t } from '@/lib/i18n';
import { getApiBaseUrl } from '../../../lib/api-url';

import WorkspaceHeaderBar from './components/WorkspaceHeaderBar';

import type { Workspace } from './workspace-page.types';

const API_URL = getApiBaseUrl();
const WorkspaceChat = dynamic(() => import('../../../components/WorkspaceChat'), { ssr: false });
const WorkspaceLeftSidebar = dynamic(() => import('./components/WorkspaceLeftSidebar'), { ssr: false });
const WorkspaceRightSidebar = dynamic(() => import('./components/WorkspaceRightSidebar'), { ssr: false });
const WorkspaceModals = dynamic(() => import('./components/WorkspaceModals'), { ssr: false });

class WorkspaceChunkBoundary extends React.Component<
  { children: React.ReactNode; fallback: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode; fallback: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error('[WorkspacePage] Failed to load workspace panel:', error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

function WorkspaceSidebarPlaceholder({ side }: { side: 'left' | 'right' }) {
  const borderClass = side === 'left' ? 'border-r' : 'border-l';
  return (
    <div
      aria-hidden="true"
      className={`w-80 ${borderClass} dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex-shrink-0`}
    />
  );
}

// Internal component that uses Context data
function WorkspacePageContent({ workspaceId }: { workspaceId: string }) {
  const contextData = useWorkspaceData();

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
  const [leftPanelReady, setLeftPanelReady] = useState(false);
  const [rightPanelReady, setRightPanelReady] = useState(false);

  // UI state - modals and dialogs
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [showSystemTools, setShowSystemTools] = useState(false);
  const [showRuntimeModal, setShowRuntimeModal] = useState(false);
  const [showDataSourcesModal, setShowDataSourcesModal] = useState(false);

  // UI state - workbench
  const [updatingMode, setUpdatingMode] = useState(false);
  const [workbenchRefreshTrigger, setWorkbenchRefreshTrigger] = useState(0);

  // Thread state
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [isBundleOpen, setIsBundleOpen] = useState(false);

  // Workspace name editing state
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState('');

  // Workspace loading is handled by WorkspaceDataContext
  const loadWorkspace = contextData.refreshWorkspace;

  useEffect(() => {
    const leftTimeoutId = window.setTimeout(() => {
      setLeftPanelReady(true);
    }, 1200);
    const rightTimeoutId = window.setTimeout(() => {
      setRightPanelReady(true);
    }, 3500);
    return () => {
      window.clearTimeout(leftTimeoutId);
      window.clearTimeout(rightTimeoutId);
    };
  }, []);

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
          {leftPanelReady ? (
            <WorkspaceChunkBoundary fallback={<WorkspaceSidebarPlaceholder side="left" />}>
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
                onRefreshAll={() => contextData.refreshAll()}
              />
            </WorkspaceChunkBoundary>
          ) : (
            <WorkspaceSidebarPlaceholder side="left" />
          )}

          {/* Main Area - Workspace Chat */}
          <div className="flex-1 flex flex-col" style={{ minWidth: 0, overflow: 'hidden' }}>
            <WorkspaceChunkBoundary
              fallback={
                <div className="flex h-full items-center justify-center bg-surface dark:bg-gray-950 text-sm text-secondary dark:text-gray-400">
                  Workspace chat failed to load.
                </div>
              }
            >
              <WorkspaceChat
                workspaceId={workspaceId}
                apiUrl={API_URL}
                projectId={projectState.currentProject?.id}
                threadId={selectedThreadId}
                onFileAnalyzed={() => {
                  setWorkbenchRefreshTrigger(prev => prev + 1);
                }}
                executionMode={workspace?.execution_mode || 'hybrid'}
                expectedArtifacts={workspace?.expected_artifacts}
              />
            </WorkspaceChunkBoundary>
          </div>

          {/* Right Sidebar - Execution Chat (when focused) or Workspace Tools (default) */}
          {rightPanelReady ? (
            <WorkspaceChunkBoundary fallback={<WorkspaceSidebarPlaceholder side="right" />}>
              <WorkspaceRightSidebar
                workspace={workspace}
                workspaceId={workspaceId}
                apiUrl={API_URL}
                executionState={executionState}
                selectedThreadId={selectedThreadId}
                rightSidebarTab={rightSidebarTab}
                workbenchRefreshTrigger={workbenchRefreshTrigger}
                setRightSidebarTab={setRightSidebarTab}
                setSelectedArtifact={setSelectedArtifact}
                setLeftSidebarTab={setLeftSidebarTab}
                setSelectedThreadId={setSelectedThreadId}
                contextData={contextData}
              />
            </WorkspaceChunkBoundary>
          ) : (
            <WorkspaceSidebarPlaceholder side="right" />
          )}
        </div>
      </div>

      {/* Modals and Dialogs */}
      {rightPanelReady ? (
        <WorkspaceChunkBoundary fallback={null}>
          <WorkspaceModals
            workspaceId={workspaceId}
            apiUrl={API_URL}
            selectedArtifact={selectedArtifact}
            setSelectedArtifact={setSelectedArtifact}
            selectedThreadId={selectedThreadId}
            isBundleOpen={isBundleOpen}
            setIsBundleOpen={setIsBundleOpen}
          />
        </WorkspaceChunkBoundary>
      ) : null}
    </div>
  );
}

export default function WorkspacePageClient({ workspaceId }: { workspaceId: string }) {
  return <WorkspacePageContent workspaceId={workspaceId} />;
}

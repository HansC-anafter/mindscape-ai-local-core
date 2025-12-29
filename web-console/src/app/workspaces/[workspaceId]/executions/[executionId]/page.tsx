'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { WorkspaceDataProvider, useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import ExecutionInspector from '../../../components/ExecutionInspector';
import ExecutionChatPanel from '../../../components/ExecutionChatPanel';
import LeftSidebarTabs from '../../components/LeftSidebarTabs';
import TimelinePanel from '../../../components/TimelinePanel';
import { ThinkingPanel } from '@/components/workspace/ThinkingPanel';
import { ExecutionSidebar } from '@/components/execution';
import { TrainHeader } from '@/components/execution';
import { useExecutionState } from '@/hooks/useExecutionState';
import WorkspaceScopePanel from '../../../components/WorkspaceScopePanel';
import IntegratedSystemStatusCard from '@/components/IntegratedSystemStatusCard';
import WorkspaceSettingsModal from '../../components/WorkspaceSettingsModal';

import { getApiBaseUrl } from '../../../../../lib/api-url';

const API_URL = getApiBaseUrl();

function ExecutionPageContent({ workspaceId, executionId }: { workspaceId: string; executionId: string }) {
  const workspace = useWorkspaceData().workspace;
  const router = useRouter();
  const [focusedExecution, setFocusedExecution] = useState<any>(null);
  const [focusedPlaybookMetadata, setFocusedPlaybookMetadata] = useState<any>(null);
  const [leftSidebarTab, setLeftSidebarTab] = useState<'timeline' | 'outcomes' | 'background'>('timeline');
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [showSystemTools, setShowSystemTools] = useState(false);
  const [systemStatus, setSystemStatus] = useState<any>(null);
  const [showFullSettings, setShowFullSettings] = useState(false);

  // Execution state from hook (SSE-driven)
  const executionState = useExecutionState(workspaceId, API_URL);


  // Load execution and playbook metadata
  useEffect(() => {
    if (!executionId || !workspaceId) return;

    const loadExecution = async () => {
      try {
        const response = await fetch(
          `${API_URL}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (response.ok) {
          const data = await response.json();
          setFocusedExecution(data);

          // Extract project_id from execution if available
          const projectId = data.project_id || data.execution_context?.project_id;
          if (projectId) {
            setCurrentProjectId(projectId);
          }
        }
      } catch (error) {
        console.error('Failed to load execution:', error);
      }
    };

    loadExecution();
  }, [executionId, workspaceId]);

  // Load project ID from workspace primary_project_id if available (and no project loaded from execution)
  useEffect(() => {
    if (currentProjectId) return; // Don't override if project already loaded from execution

    if (workspace?.primary_project_id) {
      setCurrentProjectId(workspace.primary_project_id);
    } else {
      // If no primary_project_id, try to get the first active project
      const loadFirstProject = async () => {
        try {
          const response = await fetch(
            `${API_URL}/api/v1/workspaces/${workspaceId}/projects?state=open&limit=1`
          );
          if (response.ok) {
            const data = await response.json();
            if (data.projects && data.projects.length > 0) {
              setCurrentProjectId(data.projects[0].id);
            }
          }
        } catch (err) {
          console.error('Failed to load projects:', err);
        }
      };
      loadFirstProject();
    }
  }, [workspace?.primary_project_id, workspaceId, currentProjectId]);

  // Load system status
  useEffect(() => {
    const loadSystemStatus = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/system/status`);
        if (response.ok) {
          const status = await response.json();
          setSystemStatus(status);
        }
      } catch (err) {
        console.error('Failed to load system status:', err);
      }
    };
    loadSystemStatus();
  }, []);

  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <div className="flex flex-col h-[calc(100vh-48px)]">
        {/* Train Header - Progress Bar with Workspace Name */}
        {workspace && (
          <TrainHeader
            workspaceName={workspace.title}
            steps={executionState.trainSteps}
            progress={executionState.overallProgress}
            isExecuting={executionState.isExecuting}
            workspaceId={workspaceId}
            onWorkspaceNameEdit={() => {
              // Handle workspace name edit if needed
            }}
          />
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
                  <div className="flex flex-col h-full w-full">
                    {/* All Executions - ExecutionSidebar */}
                    <div className="flex-1 min-h-0 overflow-hidden w-full">
                      <ExecutionSidebar
                        projectId={currentProjectId || ''}
                        workspaceId={workspaceId}
                        apiUrl={API_URL}
                        currentExecutionId={executionId}
                        onSelectExecution={(executionId) => {
                          // Navigate to dedicated execution page
                          const executionUrl = `/workspaces/${workspaceId}/executions/${executionId}`;
                          router.push(executionUrl);
                        }}
                      />
                    </div>
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
                backgroundContent={
                  <ThinkingPanel
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
                    className={`border-t dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out ${
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
                                onRefresh={() => {
                                  // Reload system status
                                  fetch(`${API_URL}/api/v1/system/status`)
                                    .then(res => res.json())
                                    .then(status => setSystemStatus(status))
                                    .catch(err => console.error('Failed to refresh system status:', err));
                                }}
                              />
                            ) : (
                              <div className="text-sm text-secondary dark:text-gray-400">Loading system status...</div>
                            )}
                          </div>

                          {/* Full Settings Button */}
                          <div className="p-3 border-t dark:border-gray-700">
                            <button
                              onClick={() => setShowFullSettings(true)}
                              className="w-full px-3 py-2 text-sm text-primary dark:text-gray-300 bg-surface-secondary dark:bg-gray-800 border border-default dark:border-gray-700 rounded-md hover:bg-surface-accent dark:hover:bg-gray-700 transition-colors"
                            >
                              開啟完整設定
                            </button>
                          </div>
                        </>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Main Area - Execution Inspector */}
          <div className="flex-1 flex flex-col" style={{ minWidth: 0, overflow: 'hidden' }}>
            <ExecutionInspector
              executionId={executionId}
              workspaceId={workspaceId}
              apiUrl={API_URL}
              onClose={() => {
                // Navigate back to workspace page
                router.push(`/workspaces/${workspaceId}`);
              }}
            />
          </div>

          {/* Right Sidebar - Execution Chat */}
          <div className="w-80 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
            <div className="flex-1 overflow-hidden">
              <ExecutionChatPanel
                key={executionId}
                executionId={executionId}
                workspaceId={workspaceId}
                apiUrl={API_URL}
                playbookMetadata={focusedPlaybookMetadata}
              />
            </div>
          </div>
        </div>
      </div>

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
          // Refresh workspace data if needed
          window.location.reload();
        }}
      />
    </div>
  );
}

export default function ExecutionPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const executionId = params.executionId as string;

  if (!workspaceId || !executionId) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400">Invalid workspace or execution ID</p>
        </div>
      </div>
    );
  }

  return (
    <WorkspaceDataProvider workspaceId={workspaceId}>
      <div className="min-h-screen bg-surface dark:bg-gray-950 flex flex-col h-screen">
        <ExecutionPageContent workspaceId={workspaceId} executionId={executionId} />
      </div>
    </WorkspaceDataProvider>
  );
}


'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import ExecutionInspector from '../../../components/ExecutionInspector';
import ExecutionChatPanel from '../../../components/ExecutionChatPanel';
import LeftSidebarTabs from '../../components/LeftSidebarTabs';
import TimelinePanel from '../../../components/TimelinePanel';
import { ExecutionSidebar } from '@/components/execution';
import { TrainHeader } from '@/components/execution';
import { useExecutionState } from '@/hooks/useExecutionState';

import { getApiBaseUrl } from '../../../../../lib/api-url';

const API_URL = getApiBaseUrl();

function ExecutionPageContent({ workspaceId, executionId }: { workspaceId: string; executionId: string }) {
  const { workspace } = useWorkspaceData();
  const router = useRouter();
  const focusedPlaybookMetadata = undefined;
  const [leftSidebarTab, setLeftSidebarTab] = useState<'timeline' | 'outcomes'>('timeline');
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);

  const executionState = useExecutionState(workspaceId, API_URL);

  useEffect(() => {
    if (!executionId || !workspaceId) return;

    const loadExecution = async () => {
      try {
        const response = await fetch(
          `${API_URL}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (response.ok) {
          const data = await response.json();

          const projectId = data.project_id || data.execution_context?.project_id;
          if (projectId) {
            setCurrentProjectId(projectId);
          }
        }
      } catch {
      }
    };

    loadExecution();
  }, [executionId, workspaceId]);

  useEffect(() => {
    if (currentProjectId) return;

    if (workspace?.primary_project_id) {
      setCurrentProjectId(workspace.primary_project_id);
    } else {
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
        } catch {
        }
      };
      loadFirstProject();
    }
  }, [workspace?.primary_project_id, workspaceId, currentProjectId]);

  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <div className="flex flex-col h-[calc(100vh-48px)]">
        {workspace && (
          <TrainHeader
            workspaceName={workspace.title}
            steps={executionState.trainSteps}
            progress={executionState.overallProgress}
            isExecuting={executionState.isExecuting}
            workspaceId={workspaceId}
            onWorkspaceNameEdit={() => undefined}
          />
        )}

        <div className="flex flex-1 overflow-hidden">
          <div className="w-80 border-r dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
            <div className="flex-1 overflow-hidden min-h-0">
              <LeftSidebarTabs
                activeTab={leftSidebarTab}
                onTabChange={setLeftSidebarTab}
                timelineContent={
                  <div className="flex flex-col h-full w-full">
                    <div className="flex-1 min-h-0 overflow-hidden w-full">
                      <ExecutionSidebar
                        projectId={currentProjectId || ''}
                        workspaceId={workspaceId}
                        apiUrl={API_URL}
                        currentExecutionId={executionId}
                        onSelectExecution={(executionId) => {
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
              />
            </div>
          </div>

          <div className="flex-1 flex flex-col" style={{ minWidth: 0, overflow: 'hidden' }}>
            <ExecutionInspector
              executionId={executionId}
              workspaceId={workspaceId}
              apiUrl={API_URL}
              onClose={() => {
                router.push(`/workspaces/${workspaceId}`);
              }}
            />
          </div>

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

    </div>
  );
}

export default function ExecutionPage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;
  const executionId = params?.executionId as string;

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
    <div className="min-h-screen bg-surface dark:bg-gray-950 flex flex-col h-screen">
      <ExecutionPageContent workspaceId={workspaceId} executionId={executionId} />
    </div>
  );
}

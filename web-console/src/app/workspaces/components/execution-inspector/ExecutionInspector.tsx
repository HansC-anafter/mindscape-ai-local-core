'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { useT } from '@/lib/i18n';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { useExecutionCore } from './hooks/useExecutionCore';
import { useExecutionSteps } from './hooks/useExecutionSteps';
import { usePlaybookMetadata } from './hooks/usePlaybookMetadata';
import { useWorkflowData } from './hooks/useWorkflowData';
import { useExecutionActions } from './hooks/useExecutionActions';
import { calculateTotalSteps, extractArtifacts } from './utils/execution-inspector';
import HeaderBar from './HeaderBar';
import SummaryBar from './SummaryBar';
import StepsTimeline from './StepsTimeline';
import StepDetailPanel from './StepDetailPanel';
import WorkflowView from './WorkflowView';
import ArtifactsPane from './ArtifactsPane';
import ExecutionChatWrapper from './ExecutionChatWrapper';
import RestartConfirmDialog from './RestartConfirmDialog';
import SandboxModalWrapper from './SandboxModalWrapper';
import GovernanceTab from './GovernanceTab';
import type { ExecutionInspectorProps } from './types/execution';

export default function ExecutionInspector({
  executionId,
  workspaceId,
  apiUrl,
  onClose,
}: ExecutionInspectorProps) {
  console.log('[ExecutionInspector] Component rendered with executionId:', executionId, 'workspaceId:', workspaceId, 'apiUrl:', apiUrl);
  const t = useT();
  const workspaceData = useWorkspaceDataOptional();
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);
  const [showSandboxModal, setShowSandboxModal] = useState(false);
  const [sandboxInitialFile, setSandboxInitialFile] = useState<string | null>(null);
  const [rightPanelView, setRightPanelView] = useState<'artifacts' | 'chat' | 'governance'>('artifacts');

  // Use data hooks
  const executionCore = useExecutionCore(executionId, workspaceId, apiUrl, workspaceData as any);
  const executionSteps = useExecutionSteps(
    executionId,
    workspaceId,
    apiUrl,
    executionCore.currentStepIndex,
    executionCore.execution?.status
  );
  const playbookMetadata = usePlaybookMetadata(
    executionCore.execution,
    executionId,
    apiUrl
  );
  const workflowData = useWorkflowData(executionId, workspaceId, apiUrl);

  // Use execution actions hook
  const actions = useExecutionActions(
    executionId,
    workspaceId,
    apiUrl,
    executionCore.execution,
    {
      onExecutionUpdate: (execution) => {
        // Execution update is handled by useExecutionCore through SSE
      },
      onStepIndexUpdate: (stepIndex) => {
        executionCore.setCurrentStepIndex(stepIndex);
      },
      onError: (error) => {
        console.error('[ExecutionInspector] Action error:', error);
        alert(error.message);
      },
    }
  );

  // Calculate total steps
  const totalSteps = useMemo(() => {
    return calculateTotalSteps({
      playbookStepDefinitions: playbookMetadata.playbookStepDefinitions,
      steps: executionSteps.steps,
      execution: executionCore.execution || undefined,
    });
  }, [playbookMetadata.playbookStepDefinitions, executionSteps.steps, executionCore.execution]);

  // Fetch artifacts from API for this execution
  const [artifacts, setArtifacts] = useState<import('./types/execution').Artifact[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);

  useEffect(() => {
    if (!executionId || !workspaceId) {
      setArtifacts([]);
      return;
    }

    let cancelled = false;
    setArtifactsLoading(true);

    const fetchArtifacts = async () => {
      try {
        console.log('[ExecutionInspector] Fetching artifacts for execution:', executionId);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?limit=100`
        );
        if (cancelled) return;

        if (response.ok) {
          const data = await response.json();
          console.log('[ExecutionInspector] Received artifacts:', data.artifacts?.length || 0);
          // Filter artifacts for this execution
          const executionArtifacts = (data.artifacts || []).filter((art: any) => {
            const artExecutionId = art.execution_id || art.metadata?.execution_id || art.metadata?.navigate_to;
            const matches = artExecutionId === executionId;
            if (matches) {
              console.log('[ExecutionInspector] Found matching artifact:', art.id, art.title);
            }
            return matches;
          });
          console.log('[ExecutionInspector] Filtered artifacts for execution:', executionArtifacts.length);
          // Convert to Artifact format
          const convertedArtifacts = executionArtifacts.map((art: any) => {
            // Extract file path from metadata
            const filePath = art.metadata?.actual_file_path || art.metadata?.file_path || art.storage_ref;
            // Convert absolute path to relative path (remove sandbox base path)
            let relativePath: string | undefined = undefined;
            if (filePath) {
              // Extract relative path from absolute path
              // Example: /app/data/sandboxes/{workspace_id}/project_repo/{sandbox_id}/current/artifacts/.../file.json
              // Should become: artifacts/.../file.json
              const match = filePath.match(/current\/(.+)$/);
              if (match) {
                relativePath = match[1];
              } else {
                // Fallback: try to extract from path
                const parts = filePath.split('/');
                const currentIndex = parts.indexOf('current');
                if (currentIndex >= 0 && currentIndex < parts.length - 1) {
                  relativePath = parts.slice(currentIndex + 1).join('/');
                }
              }
            }

            return {
              id: art.id,
              name: art.title || art.name || 'Untitled',
              type: art.type || 'other',
              url: art.file_path ? `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${art.id}/file` : art.external_url,
              createdAt: art.created_at,
              stepId: art.metadata?.step_id,
              filePath: relativePath,
            };
          });
          if (!cancelled) {
            console.log('[ExecutionInspector] Setting artifacts:', convertedArtifacts.length);
            setArtifacts(convertedArtifacts);
          }
        } else {
          console.error('[ExecutionInspector] Failed to fetch artifacts:', response.status, response.statusText);
        }
      } catch (error) {
        console.error('[ExecutionInspector] Failed to fetch artifacts:', error);
        if (!cancelled) {
          setArtifacts([]);
        }
      } finally {
        if (!cancelled) {
          setArtifactsLoading(false);
        }
      }
    };

    fetchArtifacts();

    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  const latestArtifact = useMemo(() => {
    if (artifacts.length === 0) return undefined;
    const sorted = [...artifacts].sort((a, b) => {
      const timeA = a.createdAt ? new Date(a.createdAt).getTime() : 0;
      const timeB = b.createdAt ? new Date(b.createdAt).getTime() : 0;
      return timeB - timeA;
    });
    return sorted[0];
  }, [artifacts]);

  // Get current step data
  const currentStep = useMemo(() => {
    return executionSteps.steps.find(s => s.step_index === executionCore.currentStepIndex);
  }, [executionSteps.steps, executionCore.currentStepIndex]);

  const currentStepToolCalls = useMemo(() => {
    return executionSteps.toolCalls.filter(tc => tc.step_id === currentStep?.id);
  }, [executionSteps.toolCalls, currentStep?.id]);

  // Handle restart confirmation
  const handleRestartConfirm = () => {
    setShowRestartConfirm(false);
    if (executionCore.execution?.playbook_code && executionId) {
      actions.restartExecution();
    }
  };

  // Handle artifact view - open SandboxModal instead of direct file URL
  const handleArtifactView = (artifact: typeof artifacts[0]) => {
    console.log('[ExecutionInspector] handleArtifactView called with:', {
      artifact,
      artifactId: artifact?.id,
      artifactName: artifact?.name,
      artifactFilePath: artifact?.filePath,
      artifactUrl: artifact?.url,
      sandboxId: executionCore.sandboxId,
    });

    // Check if we have a sandbox ID
    if (!executionCore.sandboxId) {
      console.log('[ExecutionInspector] No sandboxId, falling back to direct URL');
      // Fallback: if no sandbox, open file directly (for external URLs or non-sandbox artifacts)
      if (artifact.url) {
        console.log('[ExecutionInspector] Opening artifact.url:', artifact.url);
        window.open(artifact.url, '_blank');
      } else if (artifact.id) {
        const downloadUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/download`;
        console.log('[ExecutionInspector] Opening download URL:', downloadUrl);
        window.open(downloadUrl, '_blank');
      }
      return;
    }

    console.log('[ExecutionInspector] Opening SandboxModal with filePath:', artifact.filePath);
    // Open SandboxModal with the artifact file
    setSandboxInitialFile(artifact.filePath || null);
    setShowSandboxModal(true);
  };

  const loading = executionCore.loading || executionSteps.loading || playbookMetadata.loading;

  return (
    <div className="h-full flex flex-col bg-surface dark:bg-gray-950">
      {/* Execution Header with Sandbox Button */}
      {executionCore.execution && (
        <HeaderBar
          execution={executionCore.execution}
          playbookTitle={playbookMetadata.playbookMetadata?.title || playbookMetadata.playbookMetadata?.playbook_code}
          workspaceName={executionCore.workspaceName}
          projectName={executionCore.projectName}
          executionRunNumber={parseInt(executionId.slice(-1), 16) % 10 + 1}
          stats={executionCore.executionStats}
          totalSteps={totalSteps}
          sandboxId={executionCore.sandboxId}
          isStopping={actions.isStopping}
          isReloading={actions.isReloading}
          onStop={actions.cancelExecution}
          onReloadPlaybook={actions.reloadPlaybook}
          onRestartExecution={() => setShowRestartConfirm(true)}
          onViewSandbox={() => setShowSandboxModal(true)}
          t={t as any}
        />
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-row overflow-hidden">
        {/* Middle Content Area */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          {loading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-500"></div>
            </div>
          ) : (
            <>
              {/* Execution Main Area with New Layout */}
              <div className="execution-main grid grid-rows-[auto,minmax(0,1fr)] gap-0 h-full flex-1 overflow-hidden">
                {/* Execution Summary Bar */}
                <SummaryBar
                  playbookCode={executionCore.execution?.playbook_code}
                  aiSummary={
                    executionCore.execution?.status === 'failed' && executionCore.execution.failure_reason
                      ? t('thisExecutionFailed', { reason: executionCore.execution.failure_reason })
                      : undefined
                  }
                  outputCount={artifacts.length}
                  onOpenInsights={() => {
                    // TODO: Open insights drawer/modal
                  }}
                  onOpenDrafts={() => {
                    // TODO: Open drafts drawer/modal
                  }}
                  onOpenOutputs={() => {
                    // TODO: Open outputs drawer/modal - could scroll to artifacts section
                  }}
                />

                {/* Steps Timeline & Current Step Details - Main Work Area */}
                <div className="grid grid-cols-[280px,minmax(0,1fr)] gap-0 overflow-hidden bg-surface dark:bg-gray-950 h-full">
                  {workflowData.workflowData && workflowData.workflowData.workflow_result && workflowData.workflowData.handoff_plan ? (
                    <WorkflowView
                      workflowData={workflowData.workflowData}
                      executionId={executionId}
                    />
                  ) : (
                    <>
                      {/* Left: Steps Timeline */}
                      <StepsTimeline
                        steps={executionSteps.steps}
                        playbookStepDefinitions={playbookMetadata.playbookStepDefinitions}
                        totalSteps={totalSteps}
                        currentStepIndex={executionCore.currentStepIndex}
                        executionStatus={executionCore.execution?.status}
                        onStepSelect={executionCore.setCurrentStepIndex}
                        t={t as any}
                      />

                      {/* Right: Current Step Details */}
                      <StepDetailPanel
                        steps={executionSteps.steps}
                        playbookStepDefinitions={playbookMetadata.playbookStepDefinitions}
                        totalSteps={totalSteps}
                        currentStepIndex={executionCore.currentStepIndex}
                        currentStepToolCalls={currentStepToolCalls}
                        stepEvents={executionSteps.stepEvents}
                        executionStatus={executionCore.execution?.status}
                        artifacts={artifacts}
                        workspaceId={workspaceId}
                        apiUrl={apiUrl}
                        t={t as any}
                      />
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Right: Artifacts & Playbook Inspector / Conversation / Governance */}
        <div className="w-80 flex-shrink-0 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex flex-col">
          {/* Tab Navigation */}
          <div className="flex border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setRightPanelView('artifacts')}
              className={`flex-1 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${rightPanelView === 'artifacts'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
                }`}
            >
              {t('artifacts' as any) || 'Artifacts'}
            </button>
            <button
              onClick={() => setRightPanelView('governance')}
              className={`flex-1 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${rightPanelView === 'governance'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
                }`}
            >
              {t('governance' as any) || 'Governance'}
            </button>
            <button
              onClick={() => setRightPanelView('chat')}
              className={`flex-1 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${rightPanelView === 'chat'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
                }`}
            >
              {t('chat' as any) || 'Chat'}
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-hidden">
            {rightPanelView === 'artifacts' && (
              <ArtifactsPane
                artifacts={artifacts}
                latestArtifact={latestArtifact}
                sandboxId={executionCore.sandboxId || undefined}
                apiUrl={apiUrl}
                workspaceId={workspaceId}
                onView={handleArtifactView}
                onViewSandbox={executionCore.sandboxId ? () => setShowSandboxModal(true) : undefined}
              />
            )}
            {rightPanelView === 'governance' && (
              <GovernanceTab
                executionId={executionId}
                workspaceId={workspaceId}
                apiUrl={apiUrl}
              />
            )}
            {rightPanelView === 'chat' && (
              <div className="h-full">
                <ExecutionChatWrapper
                  executionId={executionId}
                  workspaceId={workspaceId}
                  apiUrl={apiUrl}
                  playbookMetadata={playbookMetadata.playbookMetadata}
                  executionStatus={executionCore.execution?.status}
                  runNumber={executionCore.execution?.execution_id ? parseInt(executionCore.execution.execution_id.slice(-4), 16) % 1000 : 1}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Restart Confirmation Dialog */}
      <RestartConfirmDialog
        isOpen={showRestartConfirm}
        onClose={() => setShowRestartConfirm(false)}
        onConfirm={handleRestartConfirm}
        t={t as any}
      />

      {/* Sandbox Modal */}
      <SandboxModalWrapper
        isOpen={showSandboxModal}
        onClose={() => {
          setShowSandboxModal(false);
          setSandboxInitialFile(null);
        }}
        workspaceId={workspaceId}
        sandboxId={executionCore.sandboxId || ''}
        projectId={executionCore.projectId || undefined}
        executionId={executionId}
        initialFile={sandboxInitialFile}
      />
    </div>
  );
}

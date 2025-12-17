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

  // Use data hooks
  const executionCore = useExecutionCore(executionId, workspaceId, apiUrl, workspaceData);
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
      execution: executionCore.execution,
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
          const convertedArtifacts = executionArtifacts.map((art: any) => ({
            id: art.id,
            name: art.title || art.name || 'Untitled',
            type: art.type || 'other',
            url: art.file_path ? `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${art.id}/file` : art.external_url,
            createdAt: art.created_at,
            stepId: art.metadata?.step_id,
          }));
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

  // Handle artifact view
  const handleArtifactView = (artifact: typeof artifacts[0]) => {
    if (artifact.url) {
      window.open(artifact.url, '_blank');
    } else if (artifact.id) {
      window.open(`${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/download`, '_blank');
    }
  };

  const loading = executionCore.loading || executionSteps.loading || playbookMetadata.loading;

  return (
    <div className="h-full flex flex-col bg-gray-50 dark:bg-gray-950">
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
          t={t}
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
                <div className="grid grid-cols-[280px,minmax(0,1fr)] gap-0 overflow-hidden bg-gray-50 dark:bg-gray-950 h-full">
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
                        t={t}
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
                        t={t}
                      />
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Right: Artifacts & Playbook Inspector / Conversation */}
        <div className="w-80 flex-shrink-0 border-l dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col">
          {/* Artifacts List */}
          <ArtifactsPane
            artifacts={artifacts}
            latestArtifact={latestArtifact}
            sandboxId={executionCore.sandboxId || undefined}
            apiUrl={apiUrl}
            workspaceId={workspaceId}
            onView={handleArtifactView}
            onViewSandbox={executionCore.sandboxId ? () => setShowSandboxModal(true) : undefined}
          />

          {/* Playbook Inspector / Conversation */}
          <ExecutionChatWrapper
            executionId={executionId}
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            playbookMetadata={playbookMetadata.playbookMetadata}
            executionStatus={executionCore.execution?.status}
            runNumber={executionCore.execution?.execution_id ? parseInt(executionCore.execution.execution_id.slice(-4), 16) % 1000 : 1}
          />
        </div>
      </div>

      {/* Restart Confirmation Dialog */}
      <RestartConfirmDialog
        isOpen={showRestartConfirm}
        onClose={() => setShowRestartConfirm(false)}
        onConfirm={handleRestartConfirm}
        t={t}
      />

      {/* Sandbox Modal */}
      <SandboxModalWrapper
        isOpen={showSandboxModal}
        onClose={() => setShowSandboxModal(false)}
        workspaceId={workspaceId}
        sandboxId={executionCore.sandboxId || ''}
        projectId={executionCore.projectId || undefined}
        executionId={executionId}
      />
    </div>
  );
}

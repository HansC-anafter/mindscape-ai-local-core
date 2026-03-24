'use client';

import Link from 'next/link';
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { useT } from '@/lib/i18n';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { toTimestampMs } from '@/lib/time';
import { useExecutionCore } from './execution-inspector/hooks/useExecutionCore';
import { useExecutionSteps } from './execution-inspector/hooks/useExecutionSteps';
import { usePlaybookMetadata } from './execution-inspector/hooks/usePlaybookMetadata';
import { useWorkflowData } from './execution-inspector/hooks/useWorkflowData';
import { useExecutionActions } from './execution-inspector/hooks/useExecutionActions';
import { useRemoteChildExecutions } from './execution-inspector/hooks/useRemoteChildExecutions';
import { calculateTotalSteps, extractArtifacts } from './execution-inspector/utils/execution-inspector';
import HeaderBar from './execution-inspector/HeaderBar';
import SummaryBar from './execution-inspector/SummaryBar';
import StepsTimeline from './execution-inspector/StepsTimeline';
import StepDetailPanel from './execution-inspector/StepDetailPanel';
import WorkflowView from './execution-inspector/WorkflowView';
import ArtifactsPane from './execution-inspector/ArtifactsPane';
import ExecutionChatWrapper from './execution-inspector/ExecutionChatWrapper';
import RestartConfirmDialog from './execution-inspector/RestartConfirmDialog';
import SandboxModalWrapper from './execution-inspector/SandboxModalWrapper';
import type { ExecutionInspectorProps } from './execution-inspector/types/execution';

interface RelatedGovernedMemoryLink {
  eventId: string;
  memoryItemId: string;
  lifecycleStatus?: string;
  verificationStatus?: string;
}

export default function ExecutionInspector({
  executionId,
  workspaceId,
  apiUrl,
  onClose,
}: ExecutionInspectorProps) {
  const t = useT();
  const workspaceData = useWorkspaceDataOptional();
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);
  const [showSandboxModal, setShowSandboxModal] = useState(false);
  const [relatedMemory, setRelatedMemory] = useState<RelatedGovernedMemoryLink | null>(null);
  const [relatedMemoryLoading, setRelatedMemoryLoading] = useState(false);

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
  const remoteChildExecutions = useRemoteChildExecutions(
    executionId,
    workspaceId,
    apiUrl
  );

  // Stable callbacks for actions
  const handleStepIndexUpdate = useCallback((stepIndex: number) => {
    executionCore.setCurrentStepIndex(stepIndex);
  }, [executionCore]);

  const handleActionError = useCallback((error: Error) => {
    console.error('[ExecutionInspector] Action error:', error);
    alert(error.message);
  }, []);

  // Use execution actions hook
  const actions = useExecutionActions(
    executionId,
    workspaceId,
    apiUrl,
    executionCore.execution,
    {
      onExecutionUpdate: () => {
        // Execution update is handled by useExecutionCore through SSE
      },
      onStepIndexUpdate: handleStepIndexUpdate,
      onError: handleActionError,
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
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [originalArtifacts, setOriginalArtifacts] = useState<any[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);

  useEffect(() => {
    if (!executionId || !workspaceId) {
      setArtifacts([]);
      setOriginalArtifacts([]);
      return;
    }

    let cancelled = false;
    setArtifactsLoading(true);

    const fetchArtifacts = async () => {
      try {
        console.log('[ExecutionInspector] Fetching artifacts for execution:', executionId);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?limit=100&include_content=true`
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
          // Store original artifacts for IG post detection
          if (!cancelled) {
            setOriginalArtifacts(executionArtifacts);
          }
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
          setOriginalArtifacts([]);
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

  // Get current step data
  const currentStep = useMemo(() => {
    return executionSteps.steps.find(s => s.step_index === executionCore.currentStepIndex);
  }, [executionSteps.steps, executionCore.currentStepIndex]);

  // Show all artifacts in StepDetailPanel (not just current step artifacts)
  const currentStepArtifacts = useMemo(() => {
    return artifacts; // Show all artifacts in the detail panel
  }, [artifacts]);

  const latestArtifact = useMemo(() => {
    if (artifacts.length === 0) return undefined;
    const sorted = [...artifacts].sort((a, b) => {
      const timeA = toTimestampMs(a.createdAt) ?? 0;
      const timeB = toTimestampMs(b.createdAt) ?? 0;
      return timeB - timeA;
    });
    return sorted[0];
  }, [artifacts]);

  const currentStepToolCalls = useMemo(() => {
    return executionSteps.toolCalls.filter(tc => tc.step_id === currentStep?.id);
  }, [executionSteps.toolCalls, currentStep?.id]);

  const executionThreadId = useMemo(() => {
    const executionContext = executionCore.execution?.execution_context as Record<string, any> | undefined;
    const inputs = executionContext?.inputs as Record<string, any> | undefined;
    return (
      (typeof inputs?.thread_id === 'string' && inputs.thread_id) ||
      (typeof executionCore.execution?.thread_id === 'string' && executionCore.execution.thread_id) ||
      (typeof executionContext?.thread_id === 'string' && executionContext.thread_id) ||
      null
    );
  }, [executionCore.execution]);

  const relatedMemoryHref = useMemo(() => {
    if (!relatedMemory?.memoryItemId) {
      return null;
    }
    const params = new URLSearchParams();
    params.set('tab', 'memory');
    params.set('memoryId', relatedMemory.memoryItemId);
    return `/workspaces/${workspaceId}/governance?${params.toString()}`;
  }, [relatedMemory?.memoryItemId, workspaceId]);

  useEffect(() => {
    if (!workspaceId || !executionThreadId) {
      setRelatedMemory(null);
      setRelatedMemoryLoading(false);
      return;
    }

    let cancelled = false;

    const loadRelatedMemory = async () => {
      try {
        setRelatedMemoryLoading(true);
        const params = new URLSearchParams();
        params.set('event_types', 'memory_writeback');
        params.set('thread_id', executionThreadId);
        params.set('limit', '10');

        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?${params.toString()}`
        );
        if (!response.ok) {
          throw new Error(`Failed to load related governed memory: ${response.status}`);
        }

        const data = await response.json();
        const latestMemoryEvent = (data.events || []).find(
          (event: any) => typeof event?.payload?.memory_item_id === 'string' && event.payload.memory_item_id
        );

        if (!cancelled) {
          setRelatedMemory(
            latestMemoryEvent
              ? {
                  eventId: latestMemoryEvent.id,
                  memoryItemId: latestMemoryEvent.payload.memory_item_id,
                  lifecycleStatus: latestMemoryEvent.payload.lifecycle_status,
                  verificationStatus: latestMemoryEvent.payload.verification_status,
                }
              : null
          );
        }
      } catch (error) {
        console.error('[ExecutionInspector] Failed to load related governed memory:', error);
        if (!cancelled) {
          setRelatedMemory(null);
        }
      } finally {
        if (!cancelled) {
          setRelatedMemoryLoading(false);
        }
      }
    };

    void loadRelatedMemory();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, executionId, executionThreadId, workspaceId]);

  // Handle restart confirmation
  const handleRestartConfirm = useCallback(() => {
    setShowRestartConfirm(false);
    if (executionCore.execution?.playbook_code && executionId) {
      actions.restartExecution();
    }
  }, [executionCore.execution?.playbook_code, executionId, actions]);

  // Handle artifact view
  const handleArtifactView = useCallback((artifact: typeof artifacts[0]) => {
    if (artifact.url) {
      window.open(artifact.url, '_blank');
    } else if (artifact.id) {
      window.open(`${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/download`, '_blank');
    }
  }, [apiUrl, workspaceId]);

  const handleViewSandbox = useCallback(() => {
    setShowSandboxModal(true);
  }, []);

  const handleCloseSandbox = useCallback(() => {
    setShowSandboxModal(false);
  }, []);

  const handleCloseRestartConfirm = useCallback(() => {
    setShowRestartConfirm(false);
  }, []);

  const handleShowRestartConfirm = useCallback(() => {
    setShowRestartConfirm(true);
  }, []);

  const loading = executionCore.loading || executionSteps.loading || playbookMetadata.loading;
  const showExecutionChat = Boolean(
    playbookMetadata.playbookMetadata?.supports_execution_chat ??
      playbookMetadata.playbookMetadata?.metadata?.supports_execution_chat
  );
  const showRightSidebar = showExecutionChat; // Only show right sidebar for execution chat, artifacts are shown in StepDetailPanel below

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
          remoteExecutionAggregate={remoteChildExecutions.aggregate}
          isStopping={actions.isStopping}
          isReloading={actions.isReloading}
          onStop={actions.cancelExecution}
          onReloadPlaybook={actions.reloadPlaybook}
          onRestartExecution={handleShowRestartConfirm}
          onViewSandbox={handleViewSandbox}
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

                {(relatedMemoryLoading || relatedMemoryHref) && (
                  <div className="mx-4 mt-3 rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                          {t('relatedGovernedMemory' as any) || 'Related Governed Memory'}
                        </p>
                        {relatedMemoryLoading ? (
                          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                            {t('loading' as any) || 'Loading...'}
                          </p>
                        ) : (
                          <p className="mt-1 text-sm text-gray-800 dark:text-gray-100">
                            {relatedMemory?.memoryItemId}
                            {(relatedMemory?.lifecycleStatus || relatedMemory?.verificationStatus) && (
                              <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                                {[relatedMemory?.lifecycleStatus, relatedMemory?.verificationStatus]
                                  .filter(Boolean)
                                  .join(' · ')}
                              </span>
                            )}
                          </p>
                        )}
                      </div>
                      {relatedMemoryHref && (
                        <Link
                          href={relatedMemoryHref}
                          className="inline-flex items-center rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-500"
                        >
                          {t('openGovernedMemory' as any) || 'Open Governed Memory'}
                        </Link>
                      )}
                    </div>
                  </div>
                )}

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
                        artifacts={currentStepArtifacts}
                        remoteChildExecutions={remoteChildExecutions.remoteChildren}
                        workspaceId={workspaceId}
                        onViewArtifact={handleArtifactView}
                        t={t as any}
                      />
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Right: Playbook Inspector / Conversation (only if execution chat is supported) */}
        {showRightSidebar && (
          <div className="w-80 flex-shrink-0 border-l dark:border-gray-700 bg-surface-accent dark:bg-gray-900 flex flex-col">
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
        )}
      </div>

      {/* Restart Confirmation Dialog */}
      <RestartConfirmDialog
        isOpen={showRestartConfirm}
        onClose={handleCloseRestartConfirm}
        onConfirm={handleRestartConfirm}
        t={t as any}
      />

      {/* Sandbox Modal */}
      <SandboxModalWrapper
        isOpen={showSandboxModal}
        onClose={handleCloseSandbox}
        workspaceId={workspaceId}
        sandboxId={executionCore.sandboxId || ''}
        projectId={executionCore.projectId || undefined}
        executionId={executionId}
      />
    </div>
  );
}

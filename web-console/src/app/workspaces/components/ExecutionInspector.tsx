'use client';

import { useCallback, useMemo, useState } from 'react';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { useT } from '@/lib/i18n';

import { ExecutionInspectorView } from './execution-inspector/executionInspector/ExecutionInspectorView';
import {
  deriveExecutionThreadId,
  extractProductionRunId,
} from './execution-inspector/executionInspector/executionInspectorState';
import { useExecutionArtifacts } from './execution-inspector/executionInspector/useExecutionArtifacts';
import { useRelatedGovernedMemory } from './execution-inspector/executionInspector/useRelatedGovernedMemory';
import { useReviewBundleArtifacts } from './execution-inspector/executionInspector/useReviewBundleArtifacts';
import { useExecutionActions } from './execution-inspector/hooks/useExecutionActions';
import { useExecutionCore } from './execution-inspector/hooks/useExecutionCore';
import { useExecutionSteps } from './execution-inspector/hooks/useExecutionSteps';
import { usePlaybookMetadata } from './execution-inspector/hooks/usePlaybookMetadata';
import { useRemoteChildExecutions } from './execution-inspector/hooks/useRemoteChildExecutions';
import { useWorkflowData } from './execution-inspector/hooks/useWorkflowData';
import type { ExecutionInspectorProps } from './execution-inspector/types/execution';
import { calculateTotalSteps } from './execution-inspector/utils/execution-inspector';

export default function ExecutionInspector({
  apiUrl,
  executionId,
  workspaceId,
}: ExecutionInspectorProps) {
  const t = useT();
  const workspaceData = useWorkspaceDataOptional();
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);
  const [showSandboxModal, setShowSandboxModal] = useState(false);

  const executionCore = useExecutionCore(executionId, workspaceId, apiUrl, workspaceData as any);
  const executionSteps = useExecutionSteps(
    executionId,
    workspaceId,
    apiUrl,
    executionCore.currentStepIndex,
    executionCore.execution?.status,
  );
  const playbookMetadata = usePlaybookMetadata(
    executionCore.execution,
    executionId,
    apiUrl,
  );
  const workflowData = useWorkflowData(executionId, workspaceId, apiUrl);
  const remoteChildExecutions = useRemoteChildExecutions(
    executionId,
    workspaceId,
    apiUrl,
  );

  const handleStepIndexUpdate = useCallback((stepIndex: number) => {
    executionCore.setCurrentStepIndex(stepIndex);
  }, [executionCore]);

  const handleActionError = useCallback((error: Error) => {
    console.error('[ExecutionInspector] Action error:', error);
    alert(error.message);
  }, []);

  const actions = useExecutionActions(
    executionId,
    workspaceId,
    apiUrl,
    executionCore.execution,
    {
      onExecutionUpdate: () => {
        // Execution update is handled by useExecutionCore through SSE.
      },
      onStepIndexUpdate: handleStepIndexUpdate,
      onError: handleActionError,
    },
  );

  const totalSteps = useMemo(() => calculateTotalSteps({
    playbookStepDefinitions: playbookMetadata.playbookStepDefinitions,
    steps: executionSteps.steps,
    execution: executionCore.execution || undefined,
  }), [executionCore.execution, executionSteps.steps, playbookMetadata.playbookStepDefinitions]);

  const { artifacts } = useExecutionArtifacts(executionId, workspaceId, apiUrl);
  const productionRunId = useMemo(
    () => extractProductionRunId(executionCore.execution as Record<string, any> | null | undefined),
    [executionCore.execution],
  );
  const {
    handleReviewBundleArtifactUpdated,
    reviewBundleArtifacts,
    reviewBundlesLoading,
  } = useReviewBundleArtifacts(workspaceId, apiUrl, productionRunId);

  const currentStep = useMemo(() => (
    executionSteps.steps.find((step) => step.step_index === executionCore.currentStepIndex)
  ), [executionCore.currentStepIndex, executionSteps.steps]);

  const currentStepArtifacts = useMemo(() => artifacts, [artifacts]);
  const currentStepToolCalls = useMemo(() => (
    executionSteps.toolCalls.filter((toolCall) => toolCall.step_id === currentStep?.id)
  ), [currentStep?.id, executionSteps.toolCalls]);

  const executionThreadId = useMemo(
    () => deriveExecutionThreadId(executionCore.execution),
    [executionCore.execution],
  );
  const {
    relatedMemory,
    relatedMemoryHref,
    relatedMemoryLoading,
  } = useRelatedGovernedMemory({
    apiUrl,
    executionId,
    executionThreadId,
    workspaceId,
  });

  const handleRestartConfirm = useCallback(() => {
    setShowRestartConfirm(false);
    if (executionCore.execution?.playbook_code && executionId) {
      actions.restartExecution();
    }
  }, [actions, executionCore.execution?.playbook_code, executionId]);

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
    playbookMetadata.playbookMetadata?.supports_execution_chat
      ?? playbookMetadata.playbookMetadata?.metadata?.supports_execution_chat,
  );
  const showRightSidebar = showExecutionChat;

  return (
    <ExecutionInspectorView
      actions={actions}
      apiUrl={apiUrl}
      artifacts={artifacts}
      currentStepArtifacts={currentStepArtifacts}
      currentStepToolCalls={currentStepToolCalls}
      executionCore={executionCore}
      executionId={executionId}
      executionSteps={executionSteps}
      executionThreadId={executionThreadId}
      loading={loading}
      playbookMetadata={playbookMetadata}
      relatedMemory={relatedMemory}
      relatedMemoryHref={relatedMemoryHref}
      relatedMemoryLoading={relatedMemoryLoading}
      remoteChildExecutions={remoteChildExecutions}
      reviewBundleArtifacts={reviewBundleArtifacts}
      reviewBundlesLoading={reviewBundlesLoading}
      showExecutionChat={showExecutionChat}
      showRestartConfirm={showRestartConfirm}
      showRightSidebar={showRightSidebar}
      showSandboxModal={showSandboxModal}
      t={t as any}
      totalSteps={totalSteps}
      workflowData={workflowData}
      workspaceId={workspaceId}
      onCloseRestartConfirm={handleCloseRestartConfirm}
      onCloseSandbox={handleCloseSandbox}
      onRestartConfirm={handleRestartConfirm}
      onReviewBundleArtifactUpdated={handleReviewBundleArtifactUpdated}
      onShowRestartConfirm={handleShowRestartConfirm}
      onViewArtifact={handleArtifactView}
      onViewSandbox={handleViewSandbox}
    />
  );
}

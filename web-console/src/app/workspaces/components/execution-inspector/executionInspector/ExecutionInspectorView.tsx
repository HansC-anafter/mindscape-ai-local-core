import HeaderBar from '../HeaderBar';
import SummaryBar from '../SummaryBar';
import StepsTimeline from '../StepsTimeline';
import StepDetailPanel from '../StepDetailPanel';
import WorkflowView from '../WorkflowView';
import ExecutionChatWrapper from '../ExecutionChatWrapper';
import RestartConfirmDialog from '../RestartConfirmDialog';
import SandboxModalWrapper from '../SandboxModalWrapper';
import { GovernedMemoryPreview } from '@/components/workspace/governance/GovernedMemoryPreview';
import { MemoryImpactGraphPanel } from '@/components/workspace/governance/MemoryImpactGraphPanel';
import type { UseExecutionActionsResult } from '../hooks/useExecutionActions';
import type { UseExecutionCoreResult } from '../hooks/useExecutionCore';
import type { UseExecutionStepsResult } from '../hooks/useExecutionSteps';
import type { UsePlaybookMetadataResult } from '../hooks/usePlaybookMetadata';
import type { UseWorkflowDataResult } from '../hooks/useWorkflowData';
import type {
  Artifact,
  RelatedGovernedMemoryLink,
  RemoteChildExecution,
  RemoteExecutionAggregate,
  ReviewBundleArtifact,
  ToolCall,
} from '../types/execution';
import type { Translator } from '../stepDetailPanel/stepDetailPanelTypes';

interface ExecutionInspectorViewProps {
  actions: UseExecutionActionsResult;
  apiUrl: string;
  artifacts: Artifact[];
  currentStepArtifacts: Artifact[];
  currentStepToolCalls: ToolCall[];
  executionCore: UseExecutionCoreResult;
  executionId: string;
  executionSteps: UseExecutionStepsResult;
  executionThreadId: string | null;
  loading: boolean;
  playbookMetadata: UsePlaybookMetadataResult;
  relatedMemory: RelatedGovernedMemoryLink | null;
  relatedMemoryHref: string | null;
  relatedMemoryLoading: boolean;
  remoteChildExecutions: {
    aggregate: RemoteExecutionAggregate;
    remoteChildren: RemoteChildExecution[];
  };
  reviewBundleArtifacts: ReviewBundleArtifact[];
  reviewBundlesLoading: boolean;
  showExecutionChat: boolean;
  showRestartConfirm: boolean;
  showRightSidebar: boolean;
  showSandboxModal: boolean;
  t: Translator;
  totalSteps: number;
  workflowData: UseWorkflowDataResult;
  workspaceId: string;
  onCloseRestartConfirm: () => void;
  onCloseSandbox: () => void;
  onRestartConfirm: () => void;
  onReviewBundleArtifactUpdated: (artifact: ReviewBundleArtifact) => void;
  onShowRestartConfirm: () => void;
  onViewArtifact: (artifact: Artifact) => void;
  onViewSandbox: () => void;
}

export function ExecutionInspectorView({
  actions,
  apiUrl,
  artifacts,
  currentStepArtifacts,
  currentStepToolCalls,
  executionCore,
  executionId,
  executionSteps,
  executionThreadId,
  loading,
  playbookMetadata,
  relatedMemory,
  relatedMemoryHref,
  relatedMemoryLoading,
  remoteChildExecutions,
  reviewBundleArtifacts,
  reviewBundlesLoading,
  showExecutionChat,
  showRestartConfirm,
  showRightSidebar,
  showSandboxModal,
  t,
  totalSteps,
  workflowData,
  workspaceId,
  onCloseRestartConfirm,
  onCloseSandbox,
  onRestartConfirm,
  onReviewBundleArtifactUpdated,
  onShowRestartConfirm,
  onViewArtifact,
  onViewSandbox,
}: ExecutionInspectorViewProps) {
  return (
    <div className="h-full flex flex-col bg-surface dark:bg-gray-950">
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
          onRestartExecution={onShowRestartConfirm}
          onViewSandbox={onViewSandbox}
          t={t as any}
        />
      )}

      <div className="flex-1 flex flex-row overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          {loading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-500"></div>
            </div>
          ) : (
            <div className="execution-main grid grid-rows-[auto,minmax(0,1fr)] gap-0 h-full flex-1 overflow-hidden">
              <SummaryBar
                playbookCode={executionCore.execution?.playbook_code}
                aiSummary={
                  executionCore.execution?.status === 'failed' && executionCore.execution.failure_reason
                    ? t('thisExecutionFailed', { reason: executionCore.execution.failure_reason })
                    : undefined
                }
                outputCount={artifacts.length}
              />

              {relatedMemoryLoading && !relatedMemory ? (
                <div className="mx-4 mt-3 rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    {t('relatedGovernedMemory' as any) || 'Related Governed Memory'}
                  </p>
                  <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                    {t('loading' as any) || 'Loading...'}
                  </p>
                </div>
              ) : null}

              {(executionId || executionThreadId) && (
                <div className="mx-4 mt-3">
                  <MemoryImpactGraphPanel
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    executionId={executionId}
                    threadId={executionThreadId}
                    compact
                    title="Selected Memory Subgraph"
                    description="Shows which memory nodes were selected into context for this execution thread, plus the resulting writeback anchor."
                  />
                </div>
              )}

              {relatedMemoryHref && relatedMemory?.memoryItemId && (
                <div className="mx-4 mt-3">
                  <GovernedMemoryPreview
                    workspaceId={workspaceId}
                    memoryItemId={relatedMemory.memoryItemId}
                    apiUrl={apiUrl}
                    lifecycleStatus={relatedMemory.lifecycleStatus}
                    verificationStatus={relatedMemory.verificationStatus}
                    href={relatedMemoryHref}
                    compact
                  />
                </div>
              )}

              <div className="grid grid-cols-[280px,minmax(0,1fr)] gap-0 overflow-hidden bg-surface dark:bg-gray-950 h-full">
                {workflowData.workflowData && workflowData.workflowData.workflow_result && workflowData.workflowData.handoff_plan ? (
                  <WorkflowView
                    workflowData={workflowData.workflowData}
                    executionId={executionId}
                  />
                ) : (
                  <>
                    <StepsTimeline
                      steps={executionSteps.steps}
                      playbookStepDefinitions={playbookMetadata.playbookStepDefinitions}
                      totalSteps={totalSteps}
                      currentStepIndex={executionCore.currentStepIndex}
                      executionStatus={executionCore.execution?.status}
                      onStepSelect={executionCore.setCurrentStepIndex}
                      t={t as any}
                    />

                    <StepDetailPanel
                      steps={executionSteps.steps}
                      playbookStepDefinitions={playbookMetadata.playbookStepDefinitions}
                      totalSteps={totalSteps}
                      currentStepIndex={executionCore.currentStepIndex}
                      currentStepToolCalls={currentStepToolCalls}
                      stepEvents={executionSteps.stepEvents}
                      executionStatus={executionCore.execution?.status}
                      artifacts={currentStepArtifacts}
                      reviewBundleArtifacts={reviewBundleArtifacts}
                      reviewBundlesLoading={reviewBundlesLoading}
                      remoteChildExecutions={remoteChildExecutions.remoteChildren}
                      workspaceId={workspaceId}
                      apiUrl={apiUrl}
                      onViewArtifact={onViewArtifact}
                      onReviewBundleArtifactUpdated={onReviewBundleArtifactUpdated}
                      t={t as any}
                    />
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {showRightSidebar && (
          <div className="w-80 flex-shrink-0 border-l dark:border-gray-700 bg-surface-accent dark:bg-gray-900 flex flex-col">
            {showExecutionChat && (
              <ExecutionChatWrapper
                executionId={executionId}
                workspaceId={workspaceId}
                apiUrl={apiUrl}
                playbookMetadata={playbookMetadata.playbookMetadata}
                executionStatus={executionCore.execution?.status}
                runNumber={executionCore.execution?.execution_id ? parseInt(executionCore.execution.execution_id.slice(-4), 16) % 1000 : 1}
              />
            )}
          </div>
        )}
      </div>

      <RestartConfirmDialog
        isOpen={showRestartConfirm}
        onClose={onCloseRestartConfirm}
        onConfirm={onRestartConfirm}
        t={t as any}
      />

      <SandboxModalWrapper
        isOpen={showSandboxModal}
        onClose={onCloseSandbox}
        workspaceId={workspaceId}
        sandboxId={executionCore.sandboxId || ''}
        projectId={executionCore.projectId || undefined}
        executionId={executionId}
      />
    </div>
  );
}

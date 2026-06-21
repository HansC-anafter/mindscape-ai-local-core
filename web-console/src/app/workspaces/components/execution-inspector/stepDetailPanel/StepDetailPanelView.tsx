import React from 'react';

import type {
  Artifact,
  ExecutionStep,
  RelatedGovernedMemoryLink,
  RemoteChildExecution,
  ReviewBundleArtifact,
  StepEvent,
  ToolCall,
} from '../types/execution';
import { ArtifactsSection } from './ArtifactsSection';
import { DynamicCapabilityComponentsSection } from './DynamicCapabilityComponentsSection';
import { RemoteExecutionSection } from './RemoteExecutionSection';
import { StepEventsSection } from './StepEventsSection';
import { StepHeaderSection } from './StepHeaderSection';
import { ToolCallsSection } from './ToolCallsSection';
import { VisualAcceptanceSection } from './VisualAcceptanceSection';
import type { DynamicComponentState, StepInfo, Translator } from './stepDetailPanelTypes';

interface StepDetailPanelViewProps extends DynamicComponentState {
  artifacts: Artifact[];
  currentStep?: ExecutionStep;
  currentStepIndex: number;
  currentStepInfo?: StepInfo;
  currentStepToolCalls: ToolCall[];
  executionStatus?: string;
  relatedGovernedMemory?: RelatedGovernedMemoryLink | null;
  remoteChildrenToShow: RemoteChildExecution[];
  reviewBundleArtifacts: ReviewBundleArtifact[];
  reviewBundlesLoading: boolean;
  selectedReviewBundle: ReviewBundleArtifact | null;
  stepEvents: StepEvent[];
  t: Translator;
  onReviewBundleSelect: (artifactId: string) => void;
  onViewArtifact?: (artifact: Artifact) => void;
}

export function StepDetailPanelView({
  apiUrl,
  artifacts,
  capabilityUIComponents,
  currentStep,
  currentStepIndex,
  currentStepInfo,
  currentStepToolCalls,
  executionStatus,
  installedCapabilities,
  matchingComponentKeys,
  openModalKey,
  relatedGovernedMemory,
  remoteChildrenToShow,
  reviewBundleArtifacts,
  reviewBundlesLoading,
  selectedReviewBundle,
  stepEvents,
  workspaceId,
  t,
  onOpenModal,
  onReviewBundleSelect,
  onViewArtifact,
}: StepDetailPanelViewProps) {
  if (!currentStepInfo) {
    return (
      <div className="h-full overflow-y-auto bg-surface-secondary dark:bg-gray-800 p-3 min-w-0">
        <div className="text-center py-8 text-gray-500 dark:text-gray-300">
          {t('selectStepToViewDetails' as any) || 'Select a step to view details'}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-secondary dark:bg-gray-800 p-3 min-w-0">
      <StepHeaderSection
        currentStep={currentStep}
        currentStepIndex={currentStepIndex}
        currentStepInfo={currentStepInfo}
        executionStatus={executionStatus}
        t={t}
      />
      <RemoteExecutionSection remoteChildrenToShow={remoteChildrenToShow} />
      <StepEventsSection stepEvents={stepEvents} t={t} />
      <ToolCallsSection currentStepToolCalls={currentStepToolCalls} t={t} />

      {currentStep?.error && (
        <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded">
          <div className="text-sm font-medium text-red-700 dark:text-red-300 mb-1">
            {t('error' as any)}
          </div>
          <div className="text-sm text-red-600 dark:text-red-400">{currentStep?.error}</div>
        </div>
      )}

      <DynamicCapabilityComponentsSection
        apiUrl={apiUrl}
        capabilityUIComponents={capabilityUIComponents}
        installedCapabilities={installedCapabilities}
        matchingComponentKeys={matchingComponentKeys}
        openModalKey={openModalKey}
        workspaceId={workspaceId}
        onOpenModal={onOpenModal}
      />
      <ArtifactsSection
        apiUrl={apiUrl}
        artifacts={artifacts}
        relatedGovernedMemory={relatedGovernedMemory}
        workspaceId={workspaceId}
        t={t}
        onViewArtifact={onViewArtifact}
      />
      <VisualAcceptanceSection
        apiUrl={apiUrl}
        installedCapabilities={installedCapabilities}
        reviewBundleArtifacts={reviewBundleArtifacts}
        reviewBundlesLoading={reviewBundlesLoading}
        selectedReviewBundle={selectedReviewBundle}
        workspaceId={workspaceId}
        onReviewBundleSelect={onReviewBundleSelect}
      />
    </div>
  );
}

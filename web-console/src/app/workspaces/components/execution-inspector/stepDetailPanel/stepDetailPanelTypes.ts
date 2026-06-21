import type React from 'react';

import type {
  Artifact,
  ExecutionStep,
  PlaybookStepDefinition,
  RelatedGovernedMemoryLink,
  RemoteChildExecution,
  ReviewBundleArtifact,
  StepEvent,
  ToolCall,
} from '../types/execution';
import type { deriveAllSteps } from '../utils/execution-inspector';

export type Translator = (key: string, params?: any) => string;
export type StepInfo = ReturnType<typeof deriveAllSteps>[number];

export interface StepDetailPanelProps {
  steps: ExecutionStep[];
  playbookStepDefinitions?: PlaybookStepDefinition[];
  totalSteps?: number;
  currentStepIndex: number;
  currentStepToolCalls: ToolCall[];
  stepEvents: StepEvent[];
  executionStatus?: string;
  artifacts?: Artifact[];
  reviewBundleArtifacts?: ReviewBundleArtifact[];
  reviewBundlesLoading?: boolean;
  remoteChildExecutions?: RemoteChildExecution[];
  workspaceId?: string;
  apiUrl?: string;
  relatedGovernedMemory?: RelatedGovernedMemoryLink | null;
  onViewArtifact?: (artifact: Artifact) => void;
  onReviewBundleArtifactUpdated?: (artifact: ReviewBundleArtifact) => void;
  t: Translator;
}

export interface DynamicComponentState {
  capabilityUIComponents: Map<string, React.ComponentType<any>>;
  installedCapabilities: any[];
  matchingComponentKeys: string[];
  openModalKey: string | null;
  workspaceId?: string;
  apiUrl?: string;
  onOpenModal: (key: string | null) => void;
}

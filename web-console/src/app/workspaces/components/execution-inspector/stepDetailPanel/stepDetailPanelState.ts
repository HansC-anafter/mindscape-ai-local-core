import { buildCapabilityWorkbenchPath } from '@/lib/capability-static-hosts';

import type {
  ExecutionStep,
  PlaybookStepDefinition,
  RemoteChildExecution,
} from '../types/execution';
import { deriveAllSteps } from '../utils/execution-inspector';

export function buildCapabilityWorkbenchHref({
  workspaceId,
  capabilityCode,
  artifactId,
  runId,
  sceneId,
}: {
  workspaceId?: string;
  capabilityCode?: string | null;
  artifactId?: string;
  runId?: string;
  sceneId?: string;
}): string | null {
  const normalizedWorkspaceId = String(workspaceId || '').trim();
  const normalizedCapabilityCode = String(capabilityCode || '').trim();
  if (!normalizedWorkspaceId || !normalizedCapabilityCode) {
    return null;
  }
  const params = new URLSearchParams();
  if (artifactId) {
    params.set('artifact_id', artifactId);
  }
  if (runId) {
    params.set('run_id', runId);
  }
  if (sceneId) {
    params.set('scene_id', sceneId);
  }
  return buildCapabilityWorkbenchPath(
    normalizedWorkspaceId,
    normalizedCapabilityCode,
    { searchParams: Object.fromEntries(params.entries()) },
  );
}

export function capabilitySupportsWorkbenchRoute(
  installedCapabilities: any[],
  capabilityCode?: string | null,
): boolean {
  const normalizedCapabilityCode = String(capabilityCode || '').trim();
  if (!normalizedCapabilityCode) {
    return false;
  }
  return installedCapabilities.some((capability) => {
    const installedCode = String(capability?.code || capability?.id || '').trim();
    return (
      installedCode === normalizedCapabilityCode &&
      Array.isArray(capability?.ui_components) &&
      capability.ui_components.length > 0
    );
  });
}

export function deriveStepDetailState({
  currentStepIndex,
  playbookStepDefinitions,
  remoteChildExecutions,
  steps,
  totalSteps,
}: {
  currentStepIndex: number;
  playbookStepDefinitions?: PlaybookStepDefinition[];
  remoteChildExecutions: RemoteChildExecution[];
  steps: ExecutionStep[];
  totalSteps?: number;
}) {
  const allSteps = deriveAllSteps({
    playbookStepDefinitions,
    totalSteps,
    steps,
  });

  const executedStepsMap = new Map(steps.map((step) => [step.step_index, step]));
  const currentStep = executedStepsMap.get(currentStepIndex) || allSteps.find((step) => step.step_index === currentStepIndex)?.executed;
  const currentStepInfo = allSteps.find((step) => step.step_index === currentStepIndex);
  const currentStepNameCandidates = [
    currentStepInfo?.step_name,
    currentStep?.step_name,
    currentStep?.id,
  ]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .map((value) => value.trim().toLowerCase());
  const relatedRemoteChildren = remoteChildExecutions.filter((child) => {
    const workflowStepId = child.remote_execution_summary?.workflow_step_id;
    if (!workflowStepId) {
      return remoteChildExecutions.length === 1;
    }
    return currentStepNameCandidates.includes(workflowStepId.trim().toLowerCase());
  });
  const remoteChildrenToShow =
    relatedRemoteChildren.length > 0
      ? relatedRemoteChildren
      : remoteChildExecutions.length === 1
        ? remoteChildExecutions
        : [];

  return {
    allSteps,
    currentStep,
    currentStepInfo,
    remoteChildrenToShow,
  };
}

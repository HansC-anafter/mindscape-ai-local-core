import type {
  ExecutionSession,
  ExecutionStep,
  StageResult,
  PlaybookStepDefinition,
  Artifact,
} from '../types/execution';

export interface AllStepInfo {
  step_index: number;
  step_name: string;
  description?: string;
  executed?: ExecutionStep;
}

/**
 * Calculate total steps from playbook definitions, steps, or execution
 */
export function calculateTotalSteps({
  playbookStepDefinitions,
  steps,
  execution,
}: {
  playbookStepDefinitions?: PlaybookStepDefinition[];
  steps?: ExecutionStep[];
  execution?: ExecutionSession;
}): number {
  if (playbookStepDefinitions && playbookStepDefinitions.length > 0) {
    return playbookStepDefinitions.length;
  }
  if (execution?.total_steps) {
    return execution.total_steps;
  }
  if (steps && steps.length > 0) {
    return Math.max(...steps.map(s => s.step_index || s.total_steps || 0));
  }
  return execution?.current_step_index ? execution.current_step_index + 1 : 1;
}

/**
 * Derive all steps from playbook definitions or total steps
 */
export function deriveAllSteps({
  playbookStepDefinitions,
  totalSteps,
  steps,
}: {
  playbookStepDefinitions?: PlaybookStepDefinition[];
  totalSteps?: number;
  steps?: ExecutionStep[];
}): AllStepInfo[] {
  const allSteps: AllStepInfo[] = [];
  const executedStepsMap = new Map(steps?.map(s => [s.step_index, s]) || []);

  if (playbookStepDefinitions && playbookStepDefinitions.length > 0) {
    playbookStepDefinitions.forEach((playbookStep, index) => {
      const uniqueStepIndex = index + 1; // UI uses 1-based index
      // Backend returns 0-based step_index, so convert playbookStep.step_index and uniqueStepIndex to 0-based
      const backendStepIndexFromPlaybook = playbookStep.step_index != null ? playbookStep.step_index : null;
      const backendStepIndexFromIndex = uniqueStepIndex - 1; // Convert 1-based to 0-based
      // Try both: playbookStep.step_index (if it's 0-based) or uniqueStepIndex converted to 0-based
      const executed = executedStepsMap.get(backendStepIndexFromPlaybook) || executedStepsMap.get(backendStepIndexFromIndex);
      allSteps.push({
        step_index: uniqueStepIndex,
        step_name: playbookStep.step_name,
        description: playbookStep.description,
        executed,
      });
    });
  } else if (totalSteps && totalSteps > 0) {
    // Backend returns 0-based step_index, but UI displays 1-based
    // So we need to map: step_index 0 -> display index 1, step_index 1 -> display index 2, etc.
    for (let displayIndex = 1; displayIndex <= totalSteps; displayIndex++) {
      const backendStepIndex = displayIndex - 1; // Convert 1-based display index to 0-based backend index
      const executed = executedStepsMap.get(backendStepIndex);
      allSteps.push({
        step_index: displayIndex, // UI uses 1-based index
        step_name: executed?.step_name || `Step ${displayIndex}`,
        executed,
      });
    }
  }

  return allSteps;
}

/**
 * Extract artifacts from stage results
 */
export function extractArtifacts(stageResults: StageResult[]): Artifact[] {
  const extractedArtifacts: Artifact[] = [];

  stageResults.forEach((result) => {
    const artifactId = result.artifact_id || result.id;
    const artifactUrl =
      result.content?.url ||
      result.content?.file_url ||
      result.content?.artifact_url ||
      result.preview ||
      result.content?.path;
    const artifactName =
      result.content?.filename ||
      result.content?.name ||
      result.stage_name ||
      result.id ||
      'Artifact';

    if (artifactId || artifactUrl || result.preview) {
      extractedArtifacts.push({
        id:
          artifactId ||
          `artifact-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        name: artifactName,
        type:
          result.result_type ||
          result.content?.type ||
          (artifactName.includes('.') ? artifactName.split('.').pop() : 'file') ||
          'file',
        createdAt: result.created_at,
        url: artifactUrl,
        stepId: result.step_id,
      });
    }
  });

  return extractedArtifacts;
}

/**
 * Format duration from start and end times
 */
export function formatDuration(
  startedAt?: string,
  completedAt?: string
): string {
  if (!startedAt) {
    return '';
  }

  const start = new Date(startedAt);
  const end = completedAt ? new Date(completedAt) : new Date();
  const diffMs = end.getTime() - start.getTime();

  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((diffMs % (1000 * 60)) / 1000);

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  } else if (minutes > 0) {
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  } else {
    return `${seconds}s`;
  }
}

/**
 * Get effective step status considering execution context
 */
export function getEffectiveStepStatus(
  step: ExecutionStep,
  executionStatus?: string
): string {
  if (executionStatus?.toLowerCase() === 'failed' && step.status === 'running') {
    return 'timeout';
  }
  return step.status;
}

/**
 * Get step status color classes
 */
export function getStepStatusColor(step: ExecutionStep): string {
  if (step.status === 'completed')
    return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-700';
  if (step.status === 'running')
    return 'text-accent dark:text-blue-400 bg-accent-10 dark:bg-blue-900/30 border-accent/30 dark:border-blue-700';
  if (step.status === 'waiting_confirmation')
    return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-700';
  if (step.status === 'failed')
    return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-700';
  return 'text-gray-400 dark:text-gray-500 bg-surface-accent dark:bg-gray-800 border-default dark:border-gray-700';
}

/**
 * Get step status icon
 */
export function getStepStatusIcon(
  step: ExecutionStep,
  executionStatus?: string
): string {
  const effectiveStatus = getEffectiveStepStatus(step, executionStatus);
  switch (effectiveStatus) {
    case 'completed':
      return '✓';
    case 'running':
      return '⟳';
    case 'waiting_confirmation':
      return '⏸';
    case 'failed':
    case 'timeout':
      return '✗';
    default:
      return '○';
  }
}

/**
 * Convert 0-based step index to 1-based for UI display
 */
export function convertStepIndexTo1Based(
  currentStepIndex0Based: number,
  totalSteps?: number
): number {
  const maxStepIndex = totalSteps || currentStepIndex0Based + 1;
  const stepIndex1Based = currentStepIndex0Based + 1;
  return Math.min(Math.max(1, stepIndex1Based), maxStepIndex);
}

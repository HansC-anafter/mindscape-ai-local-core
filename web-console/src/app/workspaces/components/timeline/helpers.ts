import { parseServerTimestamp, toTimestampMs } from '@/lib/time';

import type {
  ExecutionSession,
  ExecutionStep,
  TimelineItem,
} from './types';

export function buildExecutionStepMap(
  executions: ExecutionSession[]
): Map<string, ExecutionStep[]> {
  const stepMap = new Map<string, ExecutionStep[]>();

  executions.forEach((execution) => {
    if (execution.steps && execution.steps.length > 0) {
      stepMap.set(execution.execution_id, execution.steps);
    }
  });

  return stepMap;
}

export function upsertExecutionStepMap(
  previous: Map<string, ExecutionStep[]>,
  executionId: string,
  updatedStep: ExecutionStep
): Map<string, ExecutionStep[]> {
  const next = new Map(previous);
  const steps = [...(next.get(executionId) || [])];
  const stepIndex = steps.findIndex((step) => step.id === updatedStep.id);

  if (stepIndex >= 0) {
    steps[stepIndex] = updatedStep;
  } else {
    steps.push(updatedStep);
  }

  next.set(executionId, steps);
  return next;
}

export function getCurrentExecutionStep(
  execution: ExecutionSession,
  executionSteps: Map<string, ExecutionStep[]>
): ExecutionStep | null {
  const steps = executionSteps.get(execution.execution_id) || [];
  return steps.find((step) => step.step_index === execution.current_step_index) || null;
}

export function isPendingConfirmationExecution(
  execution: ExecutionSession,
  executionSteps: Map<string, ExecutionStep[]>
): boolean {
  if (execution.status !== 'running' || !execution.paused_at) {
    return false;
  }

  const currentStep = getCurrentExecutionStep(execution, executionSteps);
  return Boolean(
    currentStep?.requires_confirmation &&
      currentStep.confirmation_status === 'pending'
  );
}

export function getTimelineExecutionBuckets(
  executions: ExecutionSession[],
  executionSteps: Map<string, ExecutionStep[]>,
  now = new Date()
) {
  const oneHourAgoMs = now.getTime() - 60 * 60 * 1000;

  const pendingConfirmationExecutions = executions
    .filter((execution) =>
      isPendingConfirmationExecution(execution, executionSteps)
    )
    .sort(
      (left, right) =>
        (toTimestampMs(right.paused_at) ?? 0) - (toTimestampMs(left.paused_at) ?? 0)
    );

  const pendingConfirmationExecutionIds = new Set(
    pendingConfirmationExecutions.map((execution) => execution.execution_id)
  );

  const runningExecutions = executions
    .filter((execution) => {
      if (execution.status !== 'running') {
        return false;
      }
      return !pendingConfirmationExecutionIds.has(execution.execution_id);
    })
    .sort(
      (left, right) =>
        (toTimestampMs(right.started_at) ?? 0) - (toTimestampMs(left.started_at) ?? 0)
    );

  const archivedExecutions = executions
    .filter((execution) => {
      if (!['succeeded', 'failed'].includes(execution.status) || !execution.created_at) {
        return false;
      }
      const createdAtMs = toTimestampMs(execution.created_at);
      return createdAtMs !== null && createdAtMs < oneHourAgoMs;
    })
    .sort(
      (left, right) =>
        (toTimestampMs(right.created_at) ?? 0) - (toTimestampMs(left.created_at) ?? 0)
    );

  return {
    pendingConfirmationExecutions,
    runningExecutions,
    archivedExecutions,
  };
}

export function getFocusedExecutionGroups(
  executions: ExecutionSession[],
  focusExecutionId: string
) {
  const currentExecution = executions.find(
    (execution) => execution.execution_id === focusExecutionId
  );

  if (!currentExecution) {
    return null;
  }

  const samePlaybookExecutions = executions
    .filter(
      (execution) =>
        execution.execution_id !== focusExecutionId &&
        execution.playbook_code === currentExecution.playbook_code
    )
    .sort(
      (left, right) =>
        (toTimestampMs(right.created_at) ?? 0) - (toTimestampMs(left.created_at) ?? 0)
    );

  const otherPlaybookExecutions = executions
    .filter((execution) => execution.playbook_code !== currentExecution.playbook_code)
    .sort(
      (left, right) =>
        (toTimestampMs(right.created_at) ?? 0) - (toTimestampMs(left.created_at) ?? 0)
    );

  return {
    currentExecution,
    samePlaybookExecutions,
    otherPlaybookExecutions,
  };
}

export function getSortedNonExecutionTimelineItems(
  timelineItems: TimelineItem[]
): TimelineItem[] {
  return timelineItems
    .filter((item) => !item.execution_id)
    .sort(
      (left, right) =>
        (toTimestampMs(right.created_at) ?? 0) - (toTimestampMs(left.created_at) ?? 0)
    );
}

export function formatTimelineItemTime(createdAt?: string): string {
  if (!createdAt) {
    return '';
  }

  const date = parseServerTimestamp(createdAt);
  if (!date) {
    return '';
  }

  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}

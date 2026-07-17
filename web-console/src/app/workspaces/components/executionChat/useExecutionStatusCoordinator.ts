'use client';

import { useCallback, useState } from 'react';

import { retryAfterMsFromResponse } from '@/hooks/executionPollingPolicy';
import { useExecutionPolling } from '@/hooks/useExecutionPolling';

interface Params {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
  executionStatus?: string | null;
}

function responseError(response: Response, label: string): Error {
  const error = new Error(`${label}:${response.status}`) as Error & { retryAfterMs?: number };
  const retryAfterMs = retryAfterMsFromResponse(response);
  if (retryAfterMs) error.retryAfterMs = retryAfterMs;
  return error;
}

export function useExecutionStatusCoordinator(params: Params) {
  const [needsContinue, setNeedsContinue] = useState(false);
  const [currentStepStatus, setCurrentStepStatus] = useState<string | null>(null);

  const pollStatus = useCallback(async (signal: AbortSignal) => {
    const [executionResponse, stepsResponse] = await Promise.all([
      fetch(
        `${params.apiUrl}/api/v1/workspaces/${params.workspaceId}/executions/${params.executionId}`,
        { signal },
      ),
      fetch(
        `${params.apiUrl}/api/v1/workspaces/${params.workspaceId}/executions/${params.executionId}/steps`,
        { signal },
      ),
    ]);
    if (!executionResponse.ok) throw responseError(executionResponse, 'execution_status_failed');
    if (!stepsResponse.ok) throw responseError(stepsResponse, 'execution_steps_failed');

    const execution = await executionResponse.json();
    const stepsData = await stepsResponse.json();
    const currentStepIndex = execution.current_step_index ?? 0;
    const currentStep = (stepsData.steps || []).find(
      (step: any) => step.step_index === currentStepIndex + 1,
    );
    const stepStatus = currentStep?.status || null;
    const executionContext = execution.task?.execution_context || execution.execution_context || {};
    const status = execution.status || execution.task?.status || params.executionStatus;
    setCurrentStepStatus(stepStatus);
    setNeedsContinue(
      status === 'waiting_confirmation'
      || status === 'paused'
      || execution.paused_at != null
      || executionContext.paused_at != null
      || stepStatus === 'waiting_confirmation'
      || (currentStep?.requires_confirmation === true
        && currentStep?.confirmation_status === 'pending'),
    );
    return { status };
  }, [params.apiUrl, params.executionId, params.executionStatus, params.workspaceId]);

  useExecutionPolling({
    executionId: params.executionId,
    workspaceId: params.workspaceId,
    apiUrl: params.apiUrl,
    onUpdate: () => undefined,
    executionStatus: params.executionStatus,
    pollIntervalMs: 10_000,
    enableSSE: true,
    enablePollingFallback: true,
    abortablePollFn: pollStatus,
  });

  return { needsContinue, currentStepStatus };
}

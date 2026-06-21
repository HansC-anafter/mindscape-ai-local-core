import { toTimestampMs } from '@/lib/time';

import type {
  Artifact,
  ExecutionSession,
  ReviewBundleArtifact,
} from '../types/execution';

export function artifactUrl(apiUrl: string, workspaceId: string, artifact: any): string | undefined {
  if (artifact.file_path) {
    return `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/file`;
  }
  return artifact.external_url || undefined;
}

export function toArtifactRecord(apiArtifact: any, apiUrl: string, workspaceId: string): Artifact {
  return {
    id: apiArtifact.id,
    name: apiArtifact.title || apiArtifact.name || 'Untitled',
    title: apiArtifact.title,
    description: apiArtifact.description,
    type: apiArtifact.type || 'other',
    url: artifactUrl(apiUrl, workspaceId, apiArtifact),
    createdAt: apiArtifact.created_at,
    updatedAt: apiArtifact.updated_at,
    stepId: apiArtifact.metadata?.step_id,
    filePath: apiArtifact.file_path || undefined,
    metadata: apiArtifact.metadata || {},
    content: apiArtifact.content ?? undefined,
    executionId: apiArtifact.execution_id,
    artifactType: apiArtifact.artifact_type || null,
  };
}

export function toReviewBundleArtifact(apiArtifact: any, apiUrl: string, workspaceId: string): ReviewBundleArtifact {
  return {
    ...toArtifactRecord(apiArtifact, apiUrl, workspaceId),
    metadata: apiArtifact.metadata || {},
    content: apiArtifact.content || {},
  };
}

export function readRunIdCandidate(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
}

export function extractProductionRunId(execution: Record<string, any> | null | undefined): string | null {
  if (!execution) {
    return null;
  }

  const executionContext = execution.execution_context || {};
  const task = execution.task || {};
  const taskExecutionContext = task.execution_context || {};
  const workflowResult = executionContext.workflow_result || {};
  const taskWorkflowResult = taskExecutionContext.workflow_result || {};
  const taskResult = task.result || {};

  const candidates = [
    taskResult?.outputs?.run_id,
    taskResult?.run_id,
    workflowResult?.outputs?.run_id,
    workflowResult?.run_id,
    taskWorkflowResult?.outputs?.run_id,
    taskWorkflowResult?.run_id,
    executionContext?.run_id,
    taskExecutionContext?.run_id,
    executionContext?.inputs?.run_id,
    task?.params?.run_id,
  ];

  for (const candidate of candidates) {
    const runId = readRunIdCandidate(candidate);
    if (runId) {
      return runId;
    }
  }
  return null;
}

export function deriveExecutionThreadId(execution: ExecutionSession | null | undefined): string | null {
  const executionContext = execution?.execution_context as Record<string, any> | undefined;
  const inputs = executionContext?.inputs as Record<string, any> | undefined;
  return (
    (typeof inputs?.thread_id === 'string' && inputs.thread_id) ||
    (typeof execution?.thread_id === 'string' && execution.thread_id) ||
    (typeof executionContext?.thread_id === 'string' && executionContext.thread_id) ||
    null
  );
}

export function getLatestArtifact(artifacts: Artifact[]): Artifact | undefined {
  if (artifacts.length === 0) {
    return undefined;
  }
  return [...artifacts].sort((left, right) => {
    const leftTime = toTimestampMs(left.createdAt) ?? 0;
    const rightTime = toTimestampMs(right.createdAt) ?? 0;
    return rightTime - leftTime;
  })[0];
}

export function filterArtifactsForExecution(
  artifacts: any[],
  apiUrl: string,
  workspaceId: string,
  executionId: string,
): Artifact[] {
  return artifacts
    .filter((artifact) => {
      const artifactExecutionId = artifact.execution_id || artifact.metadata?.execution_id || artifact.metadata?.navigate_to;
      return artifactExecutionId === executionId;
    })
    .map((artifact) => toArtifactRecord(artifact, apiUrl, workspaceId));
}

export function filterReviewBundlesForRun(
  artifacts: any[],
  apiUrl: string,
  workspaceId: string,
  productionRunId: string,
): ReviewBundleArtifact[] {
  return artifacts
    .map((artifact) => toReviewBundleArtifact(artifact, apiUrl, workspaceId))
    .filter((artifact) => {
      const runId = readRunIdCandidate(artifact.metadata?.run_id) || readRunIdCandidate(artifact.content?.run_id);
      return runId === productionRunId;
    })
    .sort((left, right) => {
      const leftTime = toTimestampMs(left.createdAt) ?? 0;
      const rightTime = toTimestampMs(right.createdAt) ?? 0;
      return rightTime - leftTime;
    });
}

export function applyReviewBundleArtifactUpdate(
  current: ReviewBundleArtifact[],
  updatedArtifact: ReviewBundleArtifact,
): ReviewBundleArtifact[] {
  const next = [...current];
  const index = next.findIndex((artifact) => artifact.id === updatedArtifact.id);
  if (index >= 0) {
    next[index] = updatedArtifact;
    return next;
  }
  return [updatedArtifact, ...next];
}

import type {
  AsOfSnapshot,
  DurableCheckpoint,
  DurableWorkflowEvent,
  DurableWorkflowSummary,
} from './types';

const SUMMARY_BUDGET_BYTES = 150 * 1024;

function workflowPath(
  apiUrl: string,
  workspaceId: string,
  suffix: string,
): string {
  return `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/${suffix}`;
}

async function readJson<T>(
  url: string,
  signal: AbortSignal,
  maxBytes = SUMMARY_BUDGET_BYTES,
): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`Durable workflow read failed (${response.status})`);
  }
  const body = await response.text();
  if (new TextEncoder().encode(body).byteLength > maxBytes) {
    throw new Error('Durable workflow response exceeded its payload budget');
  }
  return JSON.parse(body) as T;
}

export function fetchDurabilitySummary(
  apiUrl: string,
  workspaceId: string,
  executionId: string,
  signal: AbortSignal,
): Promise<DurableWorkflowSummary> {
  return readJson(
    workflowPath(
      apiUrl,
      workspaceId,
      `executions/${encodeURIComponent(executionId)}/durability`,
    ),
    signal,
  );
}

export async function fetchWorkflowEvents(
  apiUrl: string,
  workspaceId: string,
  workflowId: string,
  cursor: number,
  signal: AbortSignal,
): Promise<DurableWorkflowEvent[]> {
  const result = await readJson<{ events: DurableWorkflowEvent[] }>(
    workflowPath(
      apiUrl,
      workspaceId,
      `durable-workflows/${encodeURIComponent(workflowId)}/events?cursor=${cursor}&limit=50`,
    ),
    signal,
  );
  return result.events;
}

export async function fetchCheckpoints(
  apiUrl: string,
  workspaceId: string,
  workflowId: string,
  cursor: number,
  signal: AbortSignal,
): Promise<DurableCheckpoint[]> {
  const result = await readJson<{ checkpoints: DurableCheckpoint[] }>(
    workflowPath(
      apiUrl,
      workspaceId,
      `durable-workflows/${encodeURIComponent(workflowId)}/checkpoints?cursor=${cursor}&limit=50`,
    ),
    signal,
  );
  return result.checkpoints;
}

export function fetchAsOfSnapshot(
  apiUrl: string,
  workspaceId: string,
  workflowId: string,
  sequence: number,
  signal: AbortSignal,
): Promise<AsOfSnapshot> {
  return readJson(
    workflowPath(
      apiUrl,
      workspaceId,
      `durable-workflows/${encodeURIComponent(workflowId)}/as-of?sequence=${sequence}`,
    ),
    signal,
  );
}

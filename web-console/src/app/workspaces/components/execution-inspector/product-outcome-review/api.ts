import type {
  AsOfProductIteration,
  ProductIterationComparison,
  ProductIterationReviewSummary,
} from './types';

const SUMMARY_BUDGET_BYTES = 150 * 1024;

function workspacePath(
  apiUrl: string,
  workspaceId: string,
  suffix: string,
): string {
  return (
    `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/`
    + suffix
  );
}

async function readBudgetedJson<T>(
  response: Response,
  maxBytes = SUMMARY_BUDGET_BYTES,
): Promise<T> {
  if (!response.ok) {
    throw new Error(`Product outcome review failed (${response.status})`);
  }
  const body = await response.text();
  if (new TextEncoder().encode(body).byteLength > maxBytes) {
    throw new Error('Product outcome response exceeded its payload budget');
  }
  return JSON.parse(body) as T;
}

export function buildIterationSummaryEndpoint(
  apiUrl: string,
  workspaceId: string,
  iterationId: string,
): string {
  return workspacePath(
    apiUrl,
    workspaceId,
    `product-iterations/${encodeURIComponent(iterationId)}`,
  );
}

export async function fetchProductIterationSummary(
  apiUrl: string,
  workspaceId: string,
  iterationId: string,
  signal: AbortSignal,
): Promise<ProductIterationReviewSummary> {
  return readBudgetedJson<ProductIterationReviewSummary>(
    await fetch(
      buildIterationSummaryEndpoint(apiUrl, workspaceId, iterationId),
      { signal },
    ),
  );
}

export async function fetchProductIterationAsOf(
  apiUrl: string,
  workspaceId: string,
  iterationId: string,
  sequence: number,
  signal: AbortSignal,
): Promise<AsOfProductIteration> {
  const endpoint = buildIterationSummaryEndpoint(
    apiUrl,
    workspaceId,
    iterationId,
  );
  return readBudgetedJson<AsOfProductIteration>(
    await fetch(
      `${endpoint}/as-of?sequence=${encodeURIComponent(sequence)}`,
      { signal },
    ),
  );
}

export async function compareProductIterations(
  apiUrl: string,
  workspaceId: string,
  refs: {
    left: { iteration_id: string; sequence: number };
    right: { iteration_id: string; sequence: number };
  },
  signal: AbortSignal,
): Promise<ProductIterationComparison> {
  return readBudgetedJson<ProductIterationComparison>(
    await fetch(
      workspacePath(apiUrl, workspaceId, 'product-iterations/compare'),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(refs),
        signal,
      },
    ),
  );
}

export async function requestProductReEvaluation(
  apiUrl: string,
  workspaceId: string,
  iterationId: string,
  request: Record<string, unknown>,
  signal: AbortSignal,
): Promise<Record<string, unknown>> {
  return readBudgetedJson<Record<string, unknown>>(
    await fetch(
      `${buildIterationSummaryEndpoint(
        apiUrl,
        workspaceId,
        iterationId,
      )}/re-evaluations`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal,
      },
    ),
  );
}

export async function requestProductIterationFork(
  apiUrl: string,
  workspaceId: string,
  iterationId: string,
  request: Record<string, unknown>,
  signal: AbortSignal,
): Promise<Record<string, unknown>> {
  return readBudgetedJson<Record<string, unknown>>(
    await fetch(
      `${buildIterationSummaryEndpoint(
        apiUrl,
        workspaceId,
        iterationId,
      )}/forks`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal,
      },
    ),
  );
}

export async function fetchOutcomeObservationPage(
  apiUrl: string,
  workspaceId: string,
  iterationId: string,
  cursor: string | null,
  signal: AbortSignal,
): Promise<{
  observations: Array<Record<string, unknown>>;
  next_cursor: string | null;
}> {
  const params = new URLSearchParams({ limit: '50' });
  if (cursor) params.set('cursor', cursor);
  return readBudgetedJson(
    await fetch(
      `${buildIterationSummaryEndpoint(
        apiUrl,
        workspaceId,
        iterationId,
      )}/observations?${params.toString()}`,
      { signal },
    ),
  );
}

export async function fetchOutcomeEvaluationPage(
  apiUrl: string,
  workspaceId: string,
  iterationId: string,
  cursor: string | null,
  signal: AbortSignal,
): Promise<{
  evaluations: Array<Record<string, unknown>>;
  next_cursor: string | null;
}> {
  const params = new URLSearchParams({ limit: '50' });
  if (cursor) params.set('cursor', cursor);
  return readBudgetedJson(
    await fetch(
      `${buildIterationSummaryEndpoint(
        apiUrl,
        workspaceId,
        iterationId,
      )}/evaluations?${params.toString()}`,
      { signal },
    ),
  );
}

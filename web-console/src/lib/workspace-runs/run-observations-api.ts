export interface RunObservationPayload {
  stage?: string;
  stage_code?: string;
  stage_index?: number;
  stage_total?: number;
  prompt_id?: string;
  elapsed_seconds?: number;
  queue_running?: number;
  queue_pending?: number;
  refs_schema_ref?: string;
  stop_reason?: string;
  error_kind?: string;
  progress?: {
    current_step_index?: number;
    total_steps?: number;
    current_step_name?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface RunObservationCard {
  run_id: string;
  execution_id?: string | null;
  workspace_id: string;
  provider_code?: string | null;
  source_kind: 'external_runner';
  status: string;
  display_title?: string | null;
  summary?: string | null;
  payload?: RunObservationPayload;
  feed_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  heartbeat_at?: string | null;
  occurred_at?: string | null;
}

export interface RunObservationEvent {
  feed_id: string;
  workspace_id: string;
  run_id: string;
  execution_id?: string | null;
  provider_code?: string | null;
  status: string;
  summary?: string | null;
  source_kind: string;
  payload?: RunObservationPayload;
  occurred_at?: string | null;
}

export interface RunObservationsSummary {
  workspace_id: string;
  source_kind: 'external_runner';
  external_active_count: number;
  counts: Record<string, number>;
  cards: RunObservationCard[];
}

export interface RunObservationEventsResponse {
  workspace_id: string;
  run_id: string;
  events: RunObservationEvent[];
}

function normalizeBaseUrl(apiUrl: string): string {
  return apiUrl.replace(/\/$/, '');
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchRunObservationsSummary(params: {
  apiUrl: string;
  workspaceId: string;
  activeOnly?: boolean;
  limit?: number;
}): Promise<RunObservationsSummary> {
  const baseUrl = normalizeBaseUrl(params.apiUrl);
  const search = new URLSearchParams();
  search.set('active_only', String(params.activeOnly ?? true));
  search.set('limit', String(params.limit ?? 20));
  return fetchJson<RunObservationsSummary>(
    `${baseUrl}/api/v1/workspaces/${encodeURIComponent(params.workspaceId)}/run-observations/summary?${search.toString()}`,
  );
}

export async function fetchRunObservationEvents(params: {
  apiUrl: string;
  workspaceId: string;
  runId: string;
  limit?: number;
}): Promise<RunObservationEventsResponse> {
  const baseUrl = normalizeBaseUrl(params.apiUrl);
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  return fetchJson<RunObservationEventsResponse>(
    `${baseUrl}/api/v1/workspaces/${encodeURIComponent(params.workspaceId)}/run-observations/${encodeURIComponent(params.runId)}/events?${search.toString()}`,
  );
}

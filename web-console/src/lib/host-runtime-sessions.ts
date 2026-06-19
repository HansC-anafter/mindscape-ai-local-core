export interface HostRuntimeSession {
  id: string;
  execution_id: string;
  workspace_id: string;
  runtime_surface: 'codex_cli' | 'gemini_cli';
  runtime_id: string;
  status: string;
  cwd: string;
  active_turn_id?: string | null;
  last_event_seq: number;
  metadata?: Record<string, unknown>;
}

export interface HostRuntimeTurn {
  id: string;
  session_id: string;
  workspace_id: string;
  status: string;
  prompt_hash: string;
  compiled_prompt_hash?: string | null;
  governance_trace_ref?: string | null;
}

export interface HostRuntimeEvent {
  id?: number | null;
  workspace_id: string;
  session_id: string;
  turn_id?: string | null;
  seq?: number | null;
  event_type: string;
  item_id?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  persist?: boolean;
}

export interface HostRuntimeStatus {
  enabled: boolean;
  runtime_surfaces: string[];
  total_bridges: number;
  bridges: Array<Record<string, unknown>>;
}

export interface SharedCliBridgeServiceStatus {
  service: string;
  workspace_id: string;
  action?: string;
  supported?: boolean;
  installed?: boolean;
  loaded?: boolean;
  running?: boolean;
  state?: string;
  label?: string;
  launchd_state?: string | null;
  auto_recovery?: boolean;
  plist_path?: string;
  message?: string;
  reason?: string | null;
}

function normalizeApiUrl(apiUrl: string): string {
  return apiUrl.replace(/\/$/, '');
}

function streamBaseUrl(apiUrl: string): string {
  const base = normalizeApiUrl(apiUrl);
  if (base.startsWith('https://')) return `wss://${base.slice('https://'.length)}`;
  if (base.startsWith('http://')) return `ws://${base.slice('http://'.length)}`;
  return base;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : `Request failed: ${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

export async function fetchHostRuntimeStatus(apiUrl: string): Promise<HostRuntimeStatus> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/api/v1/host-runtime/status`);
  return parseJsonResponse<HostRuntimeStatus>(response);
}

export async function fetchSharedCliBridgeServiceStatus({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}): Promise<SharedCliBridgeServiceStatus> {
  const response = await fetch(
    `${normalizeApiUrl(apiUrl)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/agents/bridge-service`,
    { cache: 'no-store' },
  );
  return parseJsonResponse<SharedCliBridgeServiceStatus>(response);
}

export async function startSharedCliBridgeService({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}): Promise<SharedCliBridgeServiceStatus> {
  const response = await fetch(
    `${normalizeApiUrl(apiUrl)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/agents/bridge-service/start`,
    { method: 'POST', cache: 'no-store' },
  );
  return parseJsonResponse<SharedCliBridgeServiceStatus>(response);
}

export async function createHostRuntimeSession({
  apiUrl,
  workspaceId,
  cwd,
  metadata,
}: {
  apiUrl: string;
  workspaceId: string;
  cwd: string;
  metadata?: Record<string, unknown>;
}): Promise<HostRuntimeSession> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/host-runtime/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      cwd,
      runtime_surface: 'codex_cli',
      runtime_id: 'codex_cli',
      metadata: metadata || {},
    }),
  });
  const payload = await parseJsonResponse<{ session: HostRuntimeSession }>(response);
  return payload.session;
}

export async function startHostRuntimeTurn({
  apiUrl,
  workspaceId,
  sessionId,
  prompt,
  contextRef,
}: {
  apiUrl: string;
  workspaceId: string;
  sessionId: string;
  prompt: string;
  contextRef: Record<string, unknown>;
}): Promise<{ turn: HostRuntimeTurn; status: string; event?: HostRuntimeEvent; bridge_id?: string }> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/host-runtime/sessions/${encodeURIComponent(sessionId)}/turns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt,
      context_ref: contextRef,
    }),
  });
  return parseJsonResponse(response);
}

export function buildHostRuntimeStreamUrl({
  apiUrl,
  workspaceId,
  sessionId,
  lastSeq,
}: {
  apiUrl: string;
  workspaceId: string;
  sessionId: string;
  lastSeq: number;
}): string {
  return `${streamBaseUrl(apiUrl)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/host-runtime/sessions/${encodeURIComponent(sessionId)}/stream?last_seq=${encodeURIComponent(String(lastSeq))}`;
}

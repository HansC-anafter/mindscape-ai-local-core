const WORKSPACE_READINESS_GLOBAL_KEY = '__mindscapeWorkspaceReadinessPolicy';

type WorkspaceReadinessGlobal = typeof globalThis & {
  [WORKSPACE_READINESS_GLOBAL_KEY]?: Map<string, number>;
};

export const WORKSPACE_READINESS_CACHE_MS = 120_000;
export const WORKSPACE_READINESS_BACKGROUND_POLL_MS = 180_000;

export interface WorkspaceReadinessPolicyOptions {
  force?: boolean;
  hasLocalSnapshot?: boolean;
  minIntervalMs?: number;
  nowMs?: number;
}

function readinessAttempts(): Map<string, number> {
  const state = globalThis as WorkspaceReadinessGlobal;
  if (!state[WORKSPACE_READINESS_GLOBAL_KEY]) {
    state[WORKSPACE_READINESS_GLOBAL_KEY] = new Map();
  }
  return state[WORKSPACE_READINESS_GLOBAL_KEY];
}

export function clearWorkspaceReadinessPolicyForTests(): void {
  readinessAttempts().clear();
}

export function shouldRequestWorkspaceReadiness(
  workspaceId: string | null | undefined,
  options: WorkspaceReadinessPolicyOptions = {},
): boolean {
  if (!workspaceId || workspaceId === 'new') return false;
  if (options.force) return true;

  const lastAttemptMs = readinessAttempts().get(workspaceId);
  if (lastAttemptMs == null) return true;
  if (!options.hasLocalSnapshot) return true;

  const nowMs = options.nowMs ?? Date.now();
  const minIntervalMs = options.minIntervalMs ?? WORKSPACE_READINESS_CACHE_MS;
  return nowMs - lastAttemptMs >= minIntervalMs;
}

export function markWorkspaceReadinessAttempt(
  workspaceId: string | null | undefined,
  nowMs: number = Date.now(),
): void {
  if (!workspaceId || workspaceId === 'new') return;
  readinessAttempts().set(workspaceId, nowMs);
}

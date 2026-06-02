export interface WorkspaceExecutorAgentInfo {
  id: string;
  name?: string | null;
  status?: string | null;
  transport?: string | null;
  reason?: string | null;
}

export interface WorkspaceExecutorRuntimeOption {
  id: string;
  label: string;
  disabled: boolean;
  status: string;
  reason: string | null;
  isBound: boolean;
}

export interface WorkspaceExecutorRuntimeStatus {
  runtimeId: string | null;
  name: string;
  badgeLabel: 'available' | 'bound' | 'offline' | 'default';
  statusLabel: string;
  reason: string | null;
}

function cleanRuntimeId(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const cleaned = value.trim();
  return cleaned || null;
}

function runtimeName(agent: WorkspaceExecutorAgentInfo | null, runtimeId: string): string {
  return agent?.name?.trim() || runtimeId;
}

export function deriveBoundRuntimeIds(
  routeEntries: string[] = [],
  resolvedRuntime: string | null = null,
): Set<string> {
  const runtimeIds = new Set<string>();
  routeEntries.forEach((entry) => {
    const cleaned = cleanRuntimeId(entry);
    if (cleaned) {
      runtimeIds.add(cleaned);
    }
  });
  const cleanedResolvedRuntime = cleanRuntimeId(resolvedRuntime);
  if (cleanedResolvedRuntime) {
    runtimeIds.add(cleanedResolvedRuntime);
  }
  return runtimeIds;
}

export function deriveWorkspaceExecutorRuntimeOptions(
  routeEntries: string[] = [],
  resolvedRuntime: string | null = null,
  agents: WorkspaceExecutorAgentInfo[] = [],
): WorkspaceExecutorRuntimeOption[] {
  const boundRuntimeIds = deriveBoundRuntimeIds(routeEntries, resolvedRuntime);
  const agentsById = new Map<string, WorkspaceExecutorAgentInfo>();
  agents.forEach((agent) => {
    const cleaned = cleanRuntimeId(agent.id);
    if (cleaned) {
      agentsById.set(cleaned, agent);
    }
  });

  boundRuntimeIds.forEach((runtimeId) => {
    if (!agentsById.has(runtimeId)) {
      agentsById.set(runtimeId, {
        id: runtimeId,
        name: runtimeId,
        status: 'unavailable',
      });
    }
  });

  return Array.from(agentsById.values()).map((agent) => {
    const runtimeId = cleanRuntimeId(agent.id) || agent.id;
    const isBound = boundRuntimeIds.has(runtimeId);
    const isAvailable = agent.status === 'available';
    const suffix = isAvailable ? '' : isBound ? ' (bound)' : ' (unavailable)';
    return {
      id: runtimeId,
      label: `${runtimeName(agent, runtimeId)}${suffix}`,
      disabled: !isAvailable && !isBound,
      status: agent.status || 'unknown',
      reason: agent.reason || null,
      isBound,
    };
  });
}

export function deriveWorkspaceExecutorRuntimeStatus(
  selectedRuntimeId: string | null,
  routeEntries: string[] = [],
  resolvedRuntime: string | null = null,
  agents: WorkspaceExecutorAgentInfo[] = [],
): WorkspaceExecutorRuntimeStatus {
  const runtimeId = cleanRuntimeId(selectedRuntimeId);
  if (!runtimeId) {
    return {
      runtimeId: null,
      name: 'Mindscape LLM',
      badgeLabel: 'default',
      statusLabel: 'Mindscape default',
      reason: null,
    };
  }

  const boundRuntimeIds = deriveBoundRuntimeIds(routeEntries, resolvedRuntime);
  const agent = agents.find((entry) => cleanRuntimeId(entry.id) === runtimeId) || null;
  const isBound = boundRuntimeIds.has(runtimeId);

  if (agent?.status === 'available') {
    return {
      runtimeId,
      name: runtimeName(agent, runtimeId),
      badgeLabel: 'available',
      statusLabel: agent.transport ? `${agent.transport} connected` : 'available',
      reason: agent.reason || null,
    };
  }

  if (isBound) {
    return {
      runtimeId,
      name: runtimeName(agent, runtimeId),
      badgeLabel: 'bound',
      statusLabel: agent ? 'workspace-bound, bridge offline' : 'workspace-bound',
      reason: agent?.reason || null,
    };
  }

  return {
    runtimeId,
    name: runtimeName(agent, runtimeId),
    badgeLabel: 'offline',
    statusLabel: agent ? 'unavailable' : 'unknown runtime',
    reason: agent?.reason || null,
  };
}

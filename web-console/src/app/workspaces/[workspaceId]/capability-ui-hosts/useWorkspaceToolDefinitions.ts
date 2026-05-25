'use client';

import React from 'react';

import {
  fetchWorkspaceToolDefinitions,
  type WorkspaceToolDefinition,
} from '@/lib/workspace-tools/workspace-tool-registry';

interface WorkspaceToolDefinitionsCacheEntry {
  expiresAt: number;
  promise: Promise<WorkspaceToolDefinition[]>;
}

const WORKSPACE_TOOL_DEFINITIONS_TTL_MS = 10 * 60 * 1000;
const workspaceToolDefinitionsCache = new Map<string, WorkspaceToolDefinitionsCacheEntry>();

export function getWorkspaceToolDefinitions(
  apiUrl: string,
  capabilityCode: string,
): Promise<WorkspaceToolDefinition[]> {
  const key = `workspace-tools:${apiUrl}:${capabilityCode}`;
  const now = Date.now();
  const cached = workspaceToolDefinitionsCache.get(key);
  if (cached && cached.expiresAt > now) {
    return cached.promise;
  }
  const promise = fetchWorkspaceToolDefinitions({ apiUrl, capabilityCode })
    .catch((error) => {
      workspaceToolDefinitionsCache.delete(key);
      throw error;
    });
  workspaceToolDefinitionsCache.set(key, {
    expiresAt: now + WORKSPACE_TOOL_DEFINITIONS_TTL_MS,
    promise,
  });
  return promise;
}

export function useWorkspaceToolDefinitions({
  apiUrl,
  capabilityCode,
  delayMs = 2500,
}: {
  apiUrl: string;
  capabilityCode: string;
  delayMs?: number;
}) {
  const [tools, setTools] = React.useState<WorkspaceToolDefinition[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      setIsLoading(true);
      void getWorkspaceToolDefinitions(apiUrl, capabilityCode)
        .then((nextTools) => {
          if (!cancelled) {
            setTools(nextTools);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setTools([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setIsLoading(false);
          }
        });
    }, delayMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [apiUrl, capabilityCode, delayMs]);

  return { tools, isLoading };
}

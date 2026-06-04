'use client';

import React from 'react';

import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';

declare global {
  interface Window {
    __MindscapePackScopeToolContributions?: Record<string, WorkspaceToolDefinition[]>;
  }
}

interface PackScopeToolContributionsValue {
  capabilityCode: string;
  tools: WorkspaceToolDefinition[];
}

const PackScopeToolContributionsContext = React.createContext<PackScopeToolContributionsValue | null>(null);
const PACK_SCOPE_TOOL_CONTRIBUTIONS_EVENT = 'mindscape:pack-scope-tool-contributions';

function readGlobalPackScopeTools(capabilityCode?: string): WorkspaceToolDefinition[] {
  if (typeof window === 'undefined' || !capabilityCode) {
    return [];
  }
  return window.__MindscapePackScopeToolContributions?.[capabilityCode] || [];
}

function publishGlobalPackScopeTools(capabilityCode: string, tools: WorkspaceToolDefinition[]) {
  if (typeof window === 'undefined') {
    return;
  }
  window.__MindscapePackScopeToolContributions = {
    ...(window.__MindscapePackScopeToolContributions || {}),
    [capabilityCode]: tools,
  };
  window.dispatchEvent(new CustomEvent(PACK_SCOPE_TOOL_CONTRIBUTIONS_EVENT, {
    detail: { capabilityCode },
  }));
}

export function PackScopeToolContributionsProvider({
  capabilityCode,
  tools,
  children,
}: {
  capabilityCode: string;
  tools: WorkspaceToolDefinition[];
  children: React.ReactNode;
}) {
  const value = React.useMemo(() => ({
    capabilityCode,
    tools,
  }), [capabilityCode, tools]);

  React.useEffect(() => {
    publishGlobalPackScopeTools(capabilityCode, tools);
    return () => {
      publishGlobalPackScopeTools(capabilityCode, []);
    };
  }, [capabilityCode, tools]);

  return React.createElement(
    PackScopeToolContributionsContext.Provider,
    { value },
    children,
  );
}

export function usePackScopeToolContributions(capabilityCode?: string): WorkspaceToolDefinition[] {
  const value = React.useContext(PackScopeToolContributionsContext);
  const [globalTools, setGlobalTools] = React.useState<WorkspaceToolDefinition[]>(() => (
    readGlobalPackScopeTools(capabilityCode)
  ));

  React.useEffect(() => {
    setGlobalTools(readGlobalPackScopeTools(capabilityCode));
    const handleUpdate = (event: Event) => {
      const detail = (event as CustomEvent<{ capabilityCode?: string }>).detail;
      if (!detail?.capabilityCode || detail.capabilityCode === capabilityCode) {
        setGlobalTools(readGlobalPackScopeTools(capabilityCode));
      }
    };
    window.addEventListener(PACK_SCOPE_TOOL_CONTRIBUTIONS_EVENT, handleUpdate);
    return () => window.removeEventListener(PACK_SCOPE_TOOL_CONTRIBUTIONS_EVENT, handleUpdate);
  }, [capabilityCode]);

  if (value && (!capabilityCode || value.capabilityCode === capabilityCode)) {
    return value.tools;
  }
  return globalTools;
}

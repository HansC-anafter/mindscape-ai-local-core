'use client';

import React, { useEffect, useState } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';

interface WorkspaceToolExtensionSlotProps {
  workspaceId: string;
  activeToolKey: string | null;
  tools: WorkspaceToolDefinition[];
}

export default function WorkspaceToolExtensionSlot({
  workspaceId,
  activeToolKey,
  tools,
}: WorkspaceToolExtensionSlotProps) {
  const apiUrl = getApiBaseUrl();
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null);
  const activeTool = tools.find((tool) => tool.tool_key === activeToolKey) || null;

  useEffect(() => {
    let cancelled = false;
    setComponent(null);
    if (!activeTool) {
      return () => {
        cancelled = true;
      };
    }
    void import('@/lib/capability-ui-loader').then(({
      loadCapabilityUIComponent,
      primeCapabilityUIComponentMetadata,
    }) => {
      if (cancelled) {
        return null;
      }
      primeCapabilityUIComponentMetadata(
        activeTool.capability_code,
        tools.map((tool) => tool.panel_component),
      );
      return loadCapabilityUIComponent(
        activeTool.capability_code,
        activeTool.panel_component_code,
        apiUrl,
      );
    }).then((LoadedComponent) => {
      if (!cancelled) {
        setComponent(() => LoadedComponent);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeTool, apiUrl, tools]);

  return (
    <>
      {activeTool ? (
        <div className="h-full min-h-0" data-testid="workspace-tool-extension-panel">
          {Component ? (
            <Component workspaceId={workspaceId} apiUrl={apiUrl} />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-gray-500 dark:text-gray-400">
              Loading tool...
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}

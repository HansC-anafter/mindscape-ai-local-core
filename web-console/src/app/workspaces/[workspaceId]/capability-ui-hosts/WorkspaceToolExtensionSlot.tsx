'use client';

import React, { useEffect, useState } from 'react';
import { PanelRight } from 'lucide-react';

import { WorkspaceToolRailButton } from '@/components/workspace/WorkspaceToolRail';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from '@/lib/capability-ui-loader';
import {
  fetchWorkspaceToolDefinitions,
  type WorkspaceToolDefinition,
} from '@/lib/workspace-tools/workspace-tool-registry';

interface WorkspaceToolExtensionSlotProps {
  workspaceId: string;
  capabilityCode: string;
  activeToolKey: string | null;
  onActiveToolChange: (toolKey: string | null) => void;
  onToolsChange: (tools: WorkspaceToolDefinition[]) => void;
}

export default function WorkspaceToolExtensionSlot({
  workspaceId,
  capabilityCode,
  activeToolKey,
  onActiveToolChange,
  onToolsChange,
}: WorkspaceToolExtensionSlotProps) {
  const apiUrl = getApiBaseUrl();
  const [tools, setTools] = useState<WorkspaceToolDefinition[]>([]);
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null);
  const activeTool = tools.find((tool) => tool.tool_key === activeToolKey) || null;

  useEffect(() => {
    let cancelled = false;
    void fetchWorkspaceToolDefinitions({ apiUrl, capabilityCode })
      .then((nextTools) => {
        if (cancelled) {
          return;
        }
        setTools(nextTools);
        onToolsChange(nextTools);
      })
      .catch(() => {
        if (!cancelled) {
          setTools([]);
          onToolsChange([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode, onToolsChange]);

  useEffect(() => {
    let cancelled = false;
    setComponent(null);
    if (!activeTool) {
      return () => {
        cancelled = true;
      };
    }
    primeCapabilityUIComponentMetadata(
      activeTool.capability_code,
      tools.map((tool) => tool.panel_component),
    );
    void loadCapabilityUIComponent(
      activeTool.capability_code,
      activeTool.panel_component_code,
      apiUrl,
    ).then((LoadedComponent) => {
      if (!cancelled) {
        setComponent(() => LoadedComponent);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeTool, apiUrl]);

  return (
    <>
      <div data-testid="workspace-tool-extension-slot" hidden>
        {tools.map((tool) => (
          <WorkspaceToolRailButton
            key={tool.tool_key}
            label={tool.label}
            icon={<PanelRight aria-hidden="true" className="h-4 w-4" />}
            active={activeToolKey === tool.tool_key}
            testId={`workspace-tool-${tool.tool_key}`}
            onClick={() => onActiveToolChange(activeToolKey === tool.tool_key ? null : tool.tool_key)}
          />
        ))}
      </div>
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

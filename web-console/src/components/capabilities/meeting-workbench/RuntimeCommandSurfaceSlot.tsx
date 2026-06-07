'use client';

import React, { useEffect, useState } from 'react';

import { AOL_RUNTIME_COMMAND_SURFACE_SLOT } from '@/lib/workspace-tool-contributions/workspace-tool-contribution-contract';
import {
  fetchWorkspaceToolDefinitions,
  type WorkspaceToolDefinition,
} from '@/lib/workspace-tools/workspace-tool-registry';
import type { RuntimeCommandSurfaceContext } from './meetingWorkbenchTypes';

interface RuntimeCommandSurfaceSlotProps extends RuntimeCommandSurfaceContext {
  className?: string;
}

type RuntimeCommandSurfaceComponent = React.ComponentType<RuntimeCommandSurfaceContext & {
  tool: WorkspaceToolDefinition;
}>;

function firstCommandSurfaceTool(tools: WorkspaceToolDefinition[]): WorkspaceToolDefinition | null {
  return tools
    .filter((tool) => tool.slot === AOL_RUNTIME_COMMAND_SURFACE_SLOT)
    .sort((left, right) => left.order - right.order || left.tool_key.localeCompare(right.tool_key))[0] ?? null;
}

export function RuntimeCommandSurfaceSlot({
  workspaceId,
  apiUrl,
  capabilityCode,
  meetingId,
  selectedObjectRef,
  runtimeSnapshot,
  surfaceRoute,
  className = '',
}: RuntimeCommandSurfaceSlotProps) {
  const [tool, setTool] = useState<WorkspaceToolDefinition | null>(null);
  const [Component, setComponent] = useState<RuntimeCommandSurfaceComponent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTool(null);
    setComponent(null);
    setError(null);
    if (!workspaceId || !apiUrl || !capabilityCode) {
      return () => {
        cancelled = true;
      };
    }

    async function loadCommandSurface() {
      setLoading(true);
      try {
        const tools = await fetchWorkspaceToolDefinitions({ apiUrl, capabilityCode });
        if (cancelled) return;
        const nextTool = firstCommandSurfaceTool(tools);
        setTool(nextTool);
        if (!nextTool) return;
        const {
          loadCapabilityUIComponent,
          primeCapabilityUIComponentMetadata,
        } = await import('@/lib/capability-ui-loader');
        if (cancelled) return;
        primeCapabilityUIComponentMetadata(
          nextTool.capability_code,
          tools.map((candidate) => candidate.panel_component),
        );
        const LoadedComponent = await loadCapabilityUIComponent(
          nextTool.capability_code,
          nextTool.panel_component_code,
          apiUrl,
        );
        if (!cancelled && LoadedComponent) {
          setComponent(() => LoadedComponent as RuntimeCommandSurfaceComponent);
        }
      } catch (rawError) {
        if (!cancelled) {
          setError(rawError instanceof Error ? rawError.message : 'Failed to load runtime commands.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadCommandSurface();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode, workspaceId]);

  if (!loading && !error && (!tool || !Component)) {
    return null;
  }

  return (
    <div className={className} data-testid="runtime-command-surface-slot">
      {error ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300">
          {error}
        </div>
      ) : null}
      {loading ? (
        <div className="rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
          Loading runtime commands...
        </div>
      ) : null}
      {tool && Component ? (
        <Component
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          capabilityCode={capabilityCode}
          meetingId={meetingId}
          selectedObjectRef={selectedObjectRef}
          runtimeSnapshot={runtimeSnapshot}
          surfaceRoute={surfaceRoute}
          tool={tool}
        />
      ) : null}
    </div>
  );
}

export default RuntimeCommandSurfaceSlot;

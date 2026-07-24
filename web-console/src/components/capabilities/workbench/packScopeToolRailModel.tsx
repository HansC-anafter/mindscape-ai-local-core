import React from 'react';
import {
  Activity,
  Camera,
  Box,
  FileOutput,
  PanelRight,
  Pin,
  Radio,
  Route,
  Settings,
  SlidersHorizontal,
  UserPlus,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import type { CapabilityWorkbenchPlacement } from './CapabilityWorkbenchResponsiveFrame';

const ICONS: Record<string, LucideIcon> = {
  Activity,
  Camera,
  Box,
  FileOutput,
  Panel: PanelRight,
  PanelRight,
  Pin,
  Radio,
  Route,
  Settings,
  SlidersHorizontal,
  UserPlus,
  Wrench,
};

export function readStoredOrder(storageKey: string): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(storageKey) || '[]');
    return Array.isArray(parsed)
      ? parsed.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
  } catch {
    return [];
  }
}

export function persistOrder(storageKey: string, keys: string[]) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(storageKey, JSON.stringify(keys));
  }
}

export function orderTools(
  tools: WorkspaceToolDefinition[],
  orderedKeys: string[],
): WorkspaceToolDefinition[] {
  const byKey = new Map(tools.map((tool) => [tool.tool_key, tool]));
  const ordered = orderedKeys
    .map((key) => byKey.get(key))
    .filter((tool): tool is WorkspaceToolDefinition => Boolean(tool));
  const remaining = tools
    .filter((tool) => !orderedKeys.includes(tool.tool_key))
    .sort((left, right) => left.order - right.order || left.tool_key.localeCompare(right.tool_key));
  return [...ordered, ...remaining];
}

export function iconForTool(tool: WorkspaceToolDefinition) {
  const Icon = ICONS[tool.icon] || Wrench;
  return <Icon aria-hidden className="h-3.5 w-3.5" strokeWidth={1.8} />;
}

export function bindingIdForTool(tool: WorkspaceToolDefinition): string {
  return `workspace_tool:${tool.tool_key}:open`;
}

export function aolSelectBindingId(capabilityCode: string): string {
  return `workspace_tool:${capabilityCode}:aol_select`;
}

export function activePanelToggleBindingId(capabilityCode: string): string {
  return `tool_rail:workbench:${capabilityCode}:active_panel:toggle`;
}

export function toolWithEffectiveShortcut(
  tool: WorkspaceToolDefinition,
  effectiveShortcut: string | undefined,
): WorkspaceToolDefinition {
  if (tool.shortcut === effectiveShortcut) {
    return tool;
  }
  return {
    ...tool,
    shortcut: effectiveShortcut,
  };
}

export function getPackScopeToolPanelInnerClassName(panelSize: 'content' | 'full_bleed'): string {
  return panelSize === 'full_bleed'
    ? 'h-full w-full'
    : 'inline-block max-h-full max-w-full overflow-auto rounded-md border border-zinc-800 bg-zinc-950/95 text-zinc-100 shadow-xl shadow-black/25 backdrop-blur-sm';
}

export function getPackScopeToolPanelStyle({
  placement,
  panelSize,
  floatingPosition,
}: {
  placement: CapabilityWorkbenchPlacement;
  panelSize: 'content' | 'full_bleed';
  floatingPosition: { left: number; bottom: number };
}): React.CSSProperties | undefined {
  if (placement !== 'desktop') {
    return undefined;
  }
  const baseStyle: React.CSSProperties = {
    left: floatingPosition.left,
    bottom: floatingPosition.bottom,
  };
  if (panelSize === 'full_bleed') {
    return baseStyle;
  }
  return {
    ...baseStyle,
    width: 'fit-content',
    height: 'auto',
    maxHeight: 'min(70dvh, 560px)',
    minHeight: 0,
  };
}

'use client';

import React from 'react';
import {
  Activity,
  Box,
  ChevronDown,
  ChevronRight,
  GripVertical,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRight,
  Route,
  Settings,
  SlidersHorizontal,
  Wrench,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type {
  AddressableObjectHostBridge,
} from '@/lib/addressable-object-layer';
import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from '@/lib/capability-ui-loader';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';

interface PackScopeToolRailHostProps {
  workspaceId: string;
  capabilityCode: string;
  apiUrl: string;
  tools: WorkspaceToolDefinition[];
  navigationCollapsed: boolean;
  aolHost?: Pick<AddressableObjectHostBridge, 'onSelectObject'>;
  onNavigationCollapsedChange: (collapsed: boolean) => void;
  onNavigationToggleHover?: () => void;
}

const ICONS: Record<string, LucideIcon> = {
  Activity,
  Box,
  Panel: PanelRight,
  PanelRight,
  Route,
  Settings,
  SlidersHorizontal,
  Wrench,
};

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return tagName === 'input'
    || tagName === 'textarea'
    || tagName === 'select'
    || target.isContentEditable;
}

function shortcutMatches(shortcut: string | undefined, event: KeyboardEvent): boolean {
  if (!shortcut) {
    return false;
  }
  const parts = shortcut.toLowerCase().split('+').map((part) => part.trim()).filter(Boolean);
  const key = parts[parts.length - 1];
  if (!key || event.key.toLowerCase() !== key) {
    return false;
  }
  const wantsShift = parts.includes('shift');
  const wantsAlt = parts.includes('alt') || parts.includes('option');
  const wantsCtrl = parts.includes('ctrl') || parts.includes('control');
  const wantsMeta = parts.includes('meta') || parts.includes('cmd') || parts.includes('command');
  return event.shiftKey === wantsShift
    && event.altKey === wantsAlt
    && event.ctrlKey === wantsCtrl
    && event.metaKey === wantsMeta;
}

function readStoredOrder(storageKey: string): string[] {
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

function persistOrder(storageKey: string, keys: string[]) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(storageKey, JSON.stringify(keys));
  }
}

function orderTools(tools: WorkspaceToolDefinition[], orderedKeys: string[]): WorkspaceToolDefinition[] {
  const byKey = new Map(tools.map((tool) => [tool.tool_key, tool]));
  const ordered = orderedKeys
    .map((key) => byKey.get(key))
    .filter((tool): tool is WorkspaceToolDefinition => Boolean(tool));
  const remaining = tools
    .filter((tool) => !orderedKeys.includes(tool.tool_key))
    .sort((left, right) => left.order - right.order || left.tool_key.localeCompare(right.tool_key));
  return [...ordered, ...remaining];
}

function iconForTool(tool: WorkspaceToolDefinition) {
  const Icon = ICONS[tool.icon] || Wrench;
  return <Icon aria-hidden className="h-3.5 w-3.5" strokeWidth={1.8} />;
}

export function PackScopeToolRailHost({
  workspaceId,
  capabilityCode,
  apiUrl,
  tools,
  navigationCollapsed,
  aolHost,
  onNavigationCollapsedChange,
  onNavigationToggleHover,
}: PackScopeToolRailHostProps) {
  const storageKey = `workspace:${workspaceId || 'default'}:capability:${capabilityCode}:tool-order`;
  const railRef = React.useRef<HTMLElement | null>(null);
  const [orderedKeys, setOrderedKeys] = React.useState<string[]>(() => readStoredOrder(storageKey));
  const [activeToolKey, setActiveToolKey] = React.useState<string | null>(null);
  const [draggedToolKey, setDraggedToolKey] = React.useState<string | null>(null);
  const [LoadedPanel, setLoadedPanel] = React.useState<React.ComponentType<any> | null>(null);
  const [panelExpanded, setPanelExpanded] = React.useState(false);
  const [floatingPosition, setFloatingPosition] = React.useState({ left: 48, bottom: 16 });
  const orderedTools = React.useMemo(() => orderTools(tools, orderedKeys), [orderedKeys, tools]);
  const activeTool = React.useMemo(
    () => orderedTools.find((tool) => tool.tool_key === activeToolKey) || null,
    [activeToolKey, orderedTools],
  );

  React.useEffect(() => {
    setOrderedKeys(readStoredOrder(storageKey));
  }, [storageKey]);

  React.useEffect(() => {
    if (activeToolKey && !orderedTools.some((tool) => tool.tool_key === activeToolKey)) {
      setActiveToolKey(null);
    }
  }, [activeToolKey, orderedTools]);

  const updateFloatingPosition = React.useCallback(() => {
    if (typeof window === 'undefined' || !railRef.current) {
      return;
    }
    const railRect = railRef.current.getBoundingClientRect();
    const shellRect = railRef.current.parentElement?.parentElement?.getBoundingClientRect();
    setFloatingPosition({
      left: Math.max(8, Math.round(railRect.right + 8)),
      bottom: Math.max(12, Math.round(window.innerHeight - (shellRect?.bottom ?? window.innerHeight) + 12)),
    });
  }, []);

  React.useEffect(() => {
    updateFloatingPosition();
    if (typeof window === 'undefined') {
      return undefined;
    }
    window.addEventListener('resize', updateFloatingPosition);
    return () => window.removeEventListener('resize', updateFloatingPosition);
  }, [activeToolKey, navigationCollapsed, updateFloatingPosition]);

  React.useEffect(() => {
    let cancelled = false;
    setLoadedPanel(null);
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
    ).then((Component) => {
      if (!cancelled) {
        setLoadedPanel(() => Component);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeTool, apiUrl, tools]);

  const activateTool = React.useCallback((tool: WorkspaceToolDefinition) => {
    setActiveToolKey((current) => {
      const next = current === tool.tool_key ? null : tool.tool_key;
      if (next) {
        setPanelExpanded(false);
      }
      return next;
    });
  }, []);

  React.useEffect(() => {
    if (orderedTools.length === 0) {
      return undefined;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) {
        return;
      }
      const matchedTool = orderedTools.find((tool) => shortcutMatches(tool.shortcut, event));
      if (!matchedTool) {
        return;
      }
      event.preventDefault();
      setActiveToolKey(matchedTool.tool_key);
      setPanelExpanded(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [orderedTools]);

  const handleDrop = React.useCallback((targetToolKey: string) => {
    if (!draggedToolKey || draggedToolKey === targetToolKey) {
      setDraggedToolKey(null);
      return;
    }
    const keys = orderedTools.map((tool) => tool.tool_key).filter((key) => key !== draggedToolKey);
    const targetIndex = keys.indexOf(targetToolKey);
    keys.splice(targetIndex < 0 ? keys.length : targetIndex, 0, draggedToolKey);
    setOrderedKeys(keys);
    persistOrder(storageKey, keys);
    setDraggedToolKey(null);
  }, [draggedToolKey, orderedTools, storageKey]);

  return (
    <>
      <aside
        ref={railRef}
        className="flex h-full min-h-0 w-9 shrink-0 flex-col border-r border-gray-200 bg-zinc-50/95 shadow-[inset_-1px_0_0_rgba(0,0,0,0.02)] dark:border-zinc-800 dark:bg-zinc-950"
        data-testid="pack-scope-tool-rail"
      >
        <div className="flex h-8 shrink-0 items-center justify-center border-b border-gray-200 dark:border-zinc-800">
          <button
            type="button"
            aria-label={navigationCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            title={navigationCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            data-testid="pack-scope-navigation-toggle"
            onClick={() => onNavigationCollapsedChange(!navigationCollapsed)}
            onMouseEnter={onNavigationToggleHover}
            className="inline-flex h-7 w-7 items-center justify-center rounded-sm border border-transparent text-zinc-500 transition hover:border-zinc-300 hover:bg-white hover:text-zinc-950 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-zinc-400 dark:hover:border-zinc-700 dark:hover:bg-zinc-900 dark:hover:text-white"
          >
            {navigationCollapsed ? (
              <PanelLeftOpen aria-hidden className="h-3.5 w-3.5" />
            ) : (
              <PanelLeftClose aria-hidden className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-0.5 py-1.5">
          <div className="flex flex-col items-center gap-0.5">
            {orderedTools.map((tool) => (
              <div
                key={tool.tool_key}
                draggable
                onDragStart={() => setDraggedToolKey(tool.tool_key)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => handleDrop(tool.tool_key)}
                className="group relative"
              >
                <button
                  type="button"
                  aria-label={tool.label}
                  aria-pressed={activeToolKey === tool.tool_key}
                  title={tool.shortcut ? `${tool.label} (${tool.shortcut})` : tool.label}
                  data-testid={`pack-scope-tool-${tool.tool_key}`}
                  onClick={() => activateTool(tool)}
                  className={`inline-flex h-7 w-7 items-center justify-center rounded-sm border text-zinc-500 transition focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-zinc-400 ${
                    activeToolKey === tool.tool_key
                      ? 'border-blue-500 bg-white text-blue-700 shadow-sm dark:border-blue-400 dark:bg-blue-950/40 dark:text-blue-200'
                      : 'border-transparent bg-transparent hover:border-zinc-300 hover:bg-white hover:text-zinc-950 dark:hover:border-zinc-700 dark:hover:bg-zinc-900 dark:hover:text-white'
                  }`}
                >
                  {iconForTool(tool)}
                </button>
                <GripVertical
                  aria-hidden
                  className="pointer-events-none absolute -left-0.5 top-2 h-2.5 w-2.5 text-zinc-300 opacity-0 transition group-hover:opacity-100 dark:text-zinc-600"
                />
              </div>
            ))}
          </div>
        </div>
      </aside>
      {activeTool ? (
        <section
          className={`fixed z-40 overflow-hidden rounded-md border border-zinc-800 bg-zinc-950/95 text-zinc-100 shadow-xl shadow-black/25 backdrop-blur-sm ${
            panelExpanded ? 'w-[280px]' : 'max-w-[340px]'
          }`}
          data-testid="pack-scope-tool-panel"
          data-active-tool-key={activeTool.tool_key}
          data-panel-expanded={panelExpanded ? 'true' : 'false'}
          style={{
            left: floatingPosition.left,
            bottom: floatingPosition.bottom,
          }}
        >
          {LoadedPanel ? (
            <LoadedPanel
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              tool={activeTool}
              aolHost={aolHost}
              panelCollapsed={!panelExpanded}
              onPanelCollapsedChange={(collapsed: boolean) => setPanelExpanded(!collapsed)}
              onPanelClose={() => setActiveToolKey(null)}
            />
          ) : (
            <button
              type="button"
              className="flex h-8 max-w-[320px] items-center gap-2 px-2.5 text-left text-xs text-zinc-300"
              onClick={() => setPanelExpanded(true)}
            >
              {panelExpanded ? (
                <ChevronDown aria-hidden className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
              ) : (
                <ChevronRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
              )}
              <span className="min-w-0 truncate">{activeTool.label}</span>
              <X
                aria-hidden
                className="ml-auto h-3.5 w-3.5 shrink-0 text-zinc-500"
                onClick={(event) => {
                  event.stopPropagation();
                  setActiveToolKey(null);
                }}
              />
            </button>
          )}
        </section>
      ) : null}
    </>
  );
}

export default PackScopeToolRailHost;

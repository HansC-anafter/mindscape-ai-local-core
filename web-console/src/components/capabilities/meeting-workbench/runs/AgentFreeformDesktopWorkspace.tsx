import { useEffect, useState } from 'react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import type { HostRuntimeEvent, HostRuntimeSession } from '@/lib/host-runtime-sessions';

import type { AgentFreeformLayoutState, AgentFreeformPanel } from './agentFreeformLayoutModel';
import { AgentFreeformPanelContent } from './AgentFreeformPanelContent';
import type { HostRuntimeGraphContext } from './hostRuntimeGraphContext';

type FloatingPanelKey = 'composer' | 'stream';
type FloatingPanelPosition = 'left' | 'center' | 'right';

function zIndexForLayer(layer: AgentFreeformPanel['zLayer']): number {
  return layer === 'focus' ? 30 : layer === 'raised' ? 20 : 10;
}

function nextFloatingPosition(current: FloatingPanelPosition): FloatingPanelPosition {
  return current === 'left' ? 'center' : current === 'center' ? 'right' : 'left';
}

function floatingPanelPositionClass(panel: FloatingPanelKey, position: FloatingPanelPosition): string {
  if (position === 'center') {
    return panel === 'composer' ? 'bottom-5 left-1/2 -translate-x-1/2' : 'left-1/2 top-16 -translate-x-1/2';
  }
  if (position === 'right') {
    return panel === 'composer' ? 'bottom-5 right-5' : 'right-5 top-16';
  }
  return panel === 'composer' ? 'bottom-5 left-5' : 'left-5 top-16';
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
}

export function AgentFreeformDesktopWorkspace({
  apiUrl,
  layout,
  events,
  session,
  effectiveStatus,
  meetingId,
  selectedObjectRef,
  graphContext,
  isStarting,
  composerPanel,
  streamPanel,
  dockPanels,
  onSubmitPrompt,
  onSelectPanel,
}: {
  apiUrl: string;
  layout: AgentFreeformLayoutState;
  events: HostRuntimeEvent[];
  session: HostRuntimeSession | null;
  effectiveStatus: string;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
  graphContext?: HostRuntimeGraphContext | null;
  isStarting: boolean;
  composerPanel: AgentFreeformPanel | null;
  streamPanel: AgentFreeformPanel | null;
  dockPanels: AgentFreeformPanel[];
  onSubmitPrompt: (prompt: string) => void;
  onSelectPanel: (panelId: string) => void;
}) {
  const preferredDockPanel = dockPanels.find((panel) => panel.type === 'resource_state') || dockPanels[0] || null;
  const [activeDockPanelId, setActiveDockPanelId] = useState<string | null>(preferredDockPanel?.id || null);
  const activeDockPanel = dockPanels.find((panel) => panel.id === activeDockPanelId) || preferredDockPanel;
  const [canvasZoom, setCanvasZoom] = useState(1);
  const [visibleFloatingPanels, setVisibleFloatingPanels] = useState<Record<FloatingPanelKey, boolean>>({
    composer: true,
    stream: true,
  });
  const [pinnedFloatingPanels, setPinnedFloatingPanels] = useState<Record<FloatingPanelKey, boolean>>({
    composer: true,
    stream: true,
  });
  const [floatingPositions, setFloatingPositions] = useState<Record<FloatingPanelKey, FloatingPanelPosition>>({
    composer: 'left',
    stream: 'right',
  });

  useEffect(() => {
    if (!activeDockPanelId && preferredDockPanel) {
      setActiveDockPanelId(preferredDockPanel.id);
      return;
    }
    if (activeDockPanelId && !dockPanels.some((panel) => panel.id === activeDockPanelId)) {
      setActiveDockPanelId(preferredDockPanel?.id || null);
    }
  }, [activeDockPanelId, dockPanels, preferredDockPanel]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === 'c') {
        setVisibleFloatingPanels((current) => ({ ...current, composer: true }));
        setFloatingPositions((current) => ({ ...current, composer: 'center' }));
      } else if (key === 's') {
        setVisibleFloatingPanels((current) => ({ ...current, stream: true }));
        setFloatingPositions((current) => ({ ...current, stream: 'center' }));
      } else if (key === '+' || key === '=') {
        setCanvasZoom((current) => Math.min(1.8, Number((current + 0.1).toFixed(2))));
      } else if (key === '-' || key === '_') {
        setCanvasZoom((current) => Math.max(0.6, Number((current - 0.1).toFixed(2))));
      } else if (key === '0') {
        setCanvasZoom(1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  function locateFloatingPanel(panel: FloatingPanelKey) {
    setVisibleFloatingPanels((current) => ({ ...current, [panel]: true }));
    setFloatingPositions((current) => ({ ...current, [panel]: 'center' }));
  }

  function moveFloatingPanel(panel: FloatingPanelKey) {
    setFloatingPositions((current) => ({ ...current, [panel]: nextFloatingPosition(current[panel]) }));
  }

  function togglePinnedFloatingPanel(panel: FloatingPanelKey) {
    setPinnedFloatingPanels((current) => ({ ...current, [panel]: !current[panel] }));
  }

  function zoomCanvas(delta: number) {
    setCanvasZoom((current) => Math.max(0.6, Math.min(1.8, Number((current + delta).toFixed(2)))));
  }

  const panelContentProps = {
    apiUrl,
    events,
    session,
    effectiveStatus,
    meetingId,
    selectedObjectRef,
    graphContext,
    isStarting,
    onSubmitPrompt,
  };

  return (
    <div className="flex min-h-0 h-[760px] gap-3" data-testid="agent-freeform-desktop-space">
      <div
        className="relative min-h-0 flex-1 overflow-hidden rounded-md border border-slate-200 bg-white shadow-inner dark:border-slate-800 dark:bg-slate-950"
        data-testid="agent-freeform-mind-map-canvas"
      >
        <div className="absolute left-3 top-3 z-30 flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-white/95 p-1.5 shadow-sm dark:border-slate-800 dark:bg-slate-950/95">
          <button type="button" className="h-7 rounded border border-slate-200 px-2 text-[11px] font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300" data-testid="agent-freeform-call-composer" onClick={() => locateFloatingPanel('composer')}>
            Composer
          </button>
          <button type="button" className="h-7 rounded border border-slate-200 px-2 text-[11px] font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300" data-testid="agent-freeform-call-stream" onClick={() => locateFloatingPanel('stream')}>
            Stream
          </button>
          <button type="button" className="h-7 w-7 rounded border border-slate-200 text-xs font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300" data-testid="agent-freeform-zoom-out" onClick={() => zoomCanvas(-0.1)}>
            -
          </button>
          <span className="w-10 text-center text-[11px] font-semibold text-slate-500" data-testid="agent-freeform-zoom-value">
            {Math.round(canvasZoom * 100)}%
          </span>
          <button type="button" className="h-7 w-7 rounded border border-slate-200 text-xs font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300" data-testid="agent-freeform-zoom-in" onClick={() => zoomCanvas(0.1)}>
            +
          </button>
        </div>
        <div
          className="absolute inset-0"
          data-testid="agent-freeform-canvas-space"
          style={{
            backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(148, 163, 184, 0.28) 1px, transparent 0)',
            backgroundSize: `${Math.round(28 * canvasZoom)}px ${Math.round(28 * canvasZoom)}px`,
            transform: `scale(${canvasZoom})`,
          }}
        />
        {streamPanel && visibleFloatingPanels.stream ? (
          <article
            className={`absolute z-20 flex max-h-[calc(100%-5rem)] w-[min(34rem,calc(50%-2rem))] min-h-[18rem] flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950 ${floatingPanelPositionClass('stream', floatingPositions.stream)}`}
            data-testid="agent-freeform-stream-panel"
            data-panel-type={streamPanel.type}
            onClick={() => onSelectPanel(streamPanel.id)}
          >
            <FloatingPanelHeader
              title={streamPanel.title}
              panel="stream"
              pinned={pinnedFloatingPanels.stream}
              onMove={() => moveFloatingPanel('stream')}
              onPin={() => togglePinnedFloatingPanel('stream')}
            />
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <AgentFreeformPanelContent panel={streamPanel} {...panelContentProps} />
            </div>
          </article>
        ) : null}
        {composerPanel && visibleFloatingPanels.composer ? (
          <article
            className={`absolute z-20 flex min-h-0 w-[min(34rem,calc(50%-2rem))] flex-col overflow-hidden rounded-md border bg-white shadow-sm dark:bg-slate-950 ${floatingPanelPositionClass('composer', floatingPositions.composer)} ${
              layout.selectedPanelId === composerPanel.id
                ? 'border-blue-300 ring-2 ring-blue-100 dark:border-blue-700 dark:ring-blue-950'
                : 'border-slate-200 dark:border-slate-800'
            }`}
            style={{ height: composerPanel.bounds.height, zIndex: zIndexForLayer(composerPanel.zLayer) }}
            data-testid="agent-freeform-composer-dock"
            data-panel-type={composerPanel.type}
            onClick={() => onSelectPanel(composerPanel.id)}
          >
            <FloatingPanelHeader
              title={composerPanel.title}
              panel="composer"
              pinned={pinnedFloatingPanels.composer}
              onMove={() => moveFloatingPanel('composer')}
              onPin={() => togglePinnedFloatingPanel('composer')}
            />
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <AgentFreeformPanelContent panel={composerPanel} {...panelContentProps} />
            </div>
          </article>
        ) : null}
      </div>
      <aside
        className="flex w-[20rem] min-h-0 shrink-0 flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950"
        data-testid="agent-freeform-runtime-inspector"
      >
        <header className="shrink-0 border-b border-slate-200 px-3 py-3 dark:border-slate-800">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Runs Inspector
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1" data-testid="agent-freeform-inspector-tabs">
            {dockPanels.map((panel) => {
              const active = activeDockPanel?.id === panel.id;
              return (
                <button
                  key={panel.id}
                  type="button"
                  className={`h-8 rounded-md border px-2 text-left text-[11px] font-semibold ${
                    active
                      ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/50 dark:text-blue-200'
                      : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400'
                  }`}
                  aria-pressed={active}
                  data-testid={`agent-freeform-inspector-tab-${panel.id}`}
                  onClick={() => setActiveDockPanelId(panel.id)}
                >
                  <span className="block truncate">{panel.title}</span>
                </button>
              );
            })}
          </div>
        </header>
        {activeDockPanel ? (
          <article className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid={`agent-freeform-side-panel-${activeDockPanel.id}`} data-panel-type={activeDockPanel.type}>
            <header className="flex h-10 shrink-0 items-center border-b border-slate-200 px-3 dark:border-slate-800">
              <span className="truncate text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                {activeDockPanel.title}
              </span>
            </header>
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <AgentFreeformPanelContent panel={activeDockPanel} {...panelContentProps} />
            </div>
          </article>
        ) : null}
      </aside>
    </div>
  );
}

function FloatingPanelHeader({
  title,
  panel,
  pinned,
  onMove,
  onPin,
}: {
  title: string;
  panel: FloatingPanelKey;
  pinned: boolean;
  onMove: () => void;
  onPin: () => void;
}) {
  return (
    <header className="flex h-9 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
      <span className="truncate text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
        {title}
      </span>
      <div className="flex items-center gap-1">
        <button type="button" className="rounded border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-300" data-testid={`agent-freeform-move-${panel}`} onClick={(event) => { event.stopPropagation(); onMove(); }}>
          Move
        </button>
        <button type="button" className="rounded border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-300" aria-pressed={pinned} data-testid={`agent-freeform-pin-${panel}`} onClick={(event) => { event.stopPropagation(); onPin(); }}>
          Pin
        </button>
      </div>
    </header>
  );
}

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import type { HostRuntimeEvent, HostRuntimeSession } from '@/lib/host-runtime-sessions';

import type { AgentFreeformLayoutState, AgentFreeformPanel } from './agentFreeformLayoutModel';
import { AgentFreeformPanelContent } from './AgentFreeformPanelContent';
import type { HostRuntimeGraphContext } from './hostRuntimeGraphContext';

type FloatingPanelKey = 'composer' | 'stream';
type FloatingPanelCoordinates = Record<FloatingPanelKey, { left: number; top: number }>;

function zIndexForLayer(layer: AgentFreeformPanel['zLayer']): number {
  return layer === 'focus' ? 30 : layer === 'raised' ? 20 : 10;
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
}

export function AgentFreeformDesktopWorkspace({
  apiUrl,
  workspaceId,
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
  workspaceId?: string;
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
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panelRefs = useRef<Record<FloatingPanelKey, HTMLElement | null>>({
    composer: null,
    stream: null,
  });
  const shortcutPrefixRef = useRef(false);
  const preferredDockPanel = dockPanels.find((panel) => panel.type === 'resource_state') || dockPanels[0] || null;
  const [activeDockPanelId, setActiveDockPanelId] = useState<string | null>(preferredDockPanel?.id || null);
  const activeDockPanel = dockPanels.find((panel) => panel.id === activeDockPanelId) || preferredDockPanel;
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [canvasZoom, setCanvasZoom] = useState(1);
  const [visibleFloatingPanels, setVisibleFloatingPanels] = useState<Record<FloatingPanelKey, boolean>>({
    composer: true,
    stream: true,
  });
  const [pinnedFloatingPanels, setPinnedFloatingPanels] = useState<Record<FloatingPanelKey, boolean>>({
    composer: true,
    stream: true,
  });
  const [floatingCoordinates, setFloatingCoordinates] = useState<FloatingPanelCoordinates>({
    composer: { left: 20, top: 64 },
    stream: { left: 380, top: 64 },
  });

  function clampFloatingCoordinates(panel: FloatingPanelKey, coordinates: { left: number; top: number }) {
    const canvasRect = canvasRef.current?.getBoundingClientRect();
    const panelRect = panelRefs.current[panel]?.getBoundingClientRect();
    const panelWidth = panelRect?.width || 420;
    const panelHeight = panelRect?.height || (panel === 'composer' ? 184 : 360);
    if (!canvasRect) {
      return coordinates;
    }
    return {
      left: Math.max(12, Math.min(coordinates.left, Math.max(12, canvasRect.width - panelWidth - 12))),
      top: Math.max(56, Math.min(coordinates.top, Math.max(56, canvasRect.height - panelHeight - 12))),
    };
  }

  function centerFloatingCoordinates(panel: FloatingPanelKey) {
    const canvasRect = canvasRef.current?.getBoundingClientRect();
    const panelRect = panelRefs.current[panel]?.getBoundingClientRect();
    const panelWidth = panelRect?.width || 420;
    const panelHeight = panelRect?.height || (panel === 'composer' ? 184 : 360);
    if (!canvasRect) {
      return panel === 'composer' ? { left: 120, top: 80 } : { left: 120, top: 280 };
    }
    return clampFloatingCoordinates(panel, {
      left: (canvasRect.width - panelWidth) / 2,
      top: panel === 'composer'
        ? Math.max(72, (canvasRect.height - panelHeight) / 2)
        : Math.max(260, (canvasRect.height - panelHeight) / 2),
    });
  }

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
      if (key === 'g') {
        shortcutPrefixRef.current = true;
        return;
      }
      if (shortcutPrefixRef.current) {
        shortcutPrefixRef.current = false;
        if (key === 'c') {
          setVisibleFloatingPanels((current) => ({ ...current, composer: true }));
          setFloatingCoordinates((current) => ({ ...current, composer: centerFloatingCoordinates('composer') }));
        } else if (key === 's') {
          setVisibleFloatingPanels((current) => ({ ...current, stream: true }));
          setFloatingCoordinates((current) => ({ ...current, stream: centerFloatingCoordinates('stream') }));
        } else if (key === 'r') {
          setCanvasZoom(1);
        } else if (key === 'i') {
          setInspectorOpen((current) => !current);
        }
        return;
      }
      if (key === 'c') {
        setVisibleFloatingPanels((current) => ({ ...current, composer: true }));
        setFloatingCoordinates((current) => ({ ...current, composer: centerFloatingCoordinates('composer') }));
      } else if (key === 's') {
        setVisibleFloatingPanels((current) => ({ ...current, stream: true }));
        setFloatingCoordinates((current) => ({ ...current, stream: centerFloatingCoordinates('stream') }));
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
    setFloatingCoordinates((current) => ({ ...current, [panel]: centerFloatingCoordinates(panel) }));
  }

  function startFloatingPanelDrag(panel: FloatingPanelKey, event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    const canvasRect = canvasRef.current?.getBoundingClientRect();
    const panelRect = panelRefs.current[panel]?.getBoundingClientRect();
    if (!canvasRect || !panelRect) return;
    const pointerOffset = {
      x: event.clientX - panelRect.left,
      y: event.clientY - panelRect.top,
    };
    const handlePointerMove = (moveEvent: PointerEvent) => {
      const next = clampFloatingCoordinates(panel, {
        left: moveEvent.clientX - canvasRect.left - pointerOffset.x,
        top: moveEvent.clientY - canvasRect.top - pointerOffset.y,
      });
      setFloatingCoordinates((current) => ({ ...current, [panel]: next }));
    };
    const stopDrag = () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', stopDrag);
      window.removeEventListener('pointercancel', stopDrag);
    };
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', stopDrag);
    window.addEventListener('pointercancel', stopDrag);
  }

  function togglePinnedFloatingPanel(panel: FloatingPanelKey) {
    setPinnedFloatingPanels((current) => ({ ...current, [panel]: !current[panel] }));
  }

  function zoomCanvas(delta: number) {
    setCanvasZoom((current) => Math.max(0.6, Math.min(1.8, Number((current + delta).toFixed(2)))));
  }

  const panelContentProps = {
    apiUrl,
    workspaceId,
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
    <div className="relative flex min-h-0 h-[760px]" data-testid="agent-freeform-desktop-space">
      <div
        ref={canvasRef}
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
            ref={(element) => { panelRefs.current.stream = element; }}
            className="absolute z-20 flex max-h-[calc(100%-5rem)] w-[min(34rem,calc(50%-2rem))] min-h-[18rem] flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950"
            style={{
              height: streamPanel.bounds.height,
              left: floatingCoordinates.stream.left,
              top: floatingCoordinates.stream.top,
            }}
            data-testid="agent-freeform-stream-panel"
            data-panel-type={streamPanel.type}
            onClick={() => onSelectPanel(streamPanel.id)}
          >
            <FloatingPanelHeader
              title={streamPanel.title}
              panel="stream"
              pinned={pinnedFloatingPanels.stream}
              onMovePointerDown={(event) => startFloatingPanelDrag('stream', event)}
              onPin={() => togglePinnedFloatingPanel('stream')}
            />
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <AgentFreeformPanelContent panel={streamPanel} {...panelContentProps} />
            </div>
          </article>
        ) : null}
        {composerPanel && visibleFloatingPanels.composer ? (
          <article
            ref={(element) => { panelRefs.current.composer = element; }}
            className={`absolute z-20 flex min-h-0 w-[min(34rem,calc(50%-2rem))] flex-col overflow-hidden rounded-md border bg-white shadow-sm dark:bg-slate-950 ${
              layout.selectedPanelId === composerPanel.id
                ? 'border-blue-300 ring-2 ring-blue-100 dark:border-blue-700 dark:ring-blue-950'
                : 'border-slate-200 dark:border-slate-800'
            }`}
            style={{
              height: composerPanel.bounds.height,
              left: floatingCoordinates.composer.left,
              top: floatingCoordinates.composer.top,
              zIndex: zIndexForLayer(composerPanel.zLayer),
            }}
            data-testid="agent-freeform-composer-dock"
            data-panel-type={composerPanel.type}
            onClick={() => onSelectPanel(composerPanel.id)}
          >
            <FloatingPanelHeader
              title={composerPanel.title}
              panel="composer"
              pinned={pinnedFloatingPanels.composer}
              onMovePointerDown={(event) => startFloatingPanelDrag('composer', event)}
              onPin={() => togglePinnedFloatingPanel('composer')}
            />
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <AgentFreeformPanelContent panel={composerPanel} {...panelContentProps} />
            </div>
          </article>
        ) : null}
      </div>
      {!inspectorOpen ? (
        <div
          className="absolute right-3 top-3 z-40 flex max-w-[10rem] flex-col gap-1 rounded-md border border-slate-200 bg-white/95 p-1.5 shadow-sm dark:border-slate-800 dark:bg-slate-950/95"
          data-testid="agent-freeform-inspector-collapsed"
        >
          <button
            type="button"
            className="h-7 rounded border border-slate-200 px-2 text-left text-[11px] font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300"
            data-testid="agent-freeform-inspector-open"
            onClick={() => setInspectorOpen(true)}
          >
            Inspector
          </button>
          {dockPanels.slice(0, 3).map((panel) => (
            <button
              key={panel.id}
              type="button"
              className="h-7 rounded border border-slate-200 px-2 text-left text-[11px] font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-300"
              data-testid={`agent-freeform-inspector-rail-${panel.id}`}
              onClick={() => {
                setActiveDockPanelId(panel.id);
                setInspectorOpen(true);
              }}
            >
              <span className="block truncate">{panel.title}</span>
            </button>
          ))}
        </div>
      ) : null}
      {inspectorOpen ? (
        <aside
          className="absolute bottom-3 right-3 top-3 z-50 flex w-[20rem] min-h-0 flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950"
          data-testid="agent-freeform-runtime-inspector"
        >
          <header className="shrink-0 border-b border-slate-200 px-3 py-3 dark:border-slate-800">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                Runs Inspector
              </div>
              <button
                type="button"
                className="h-7 rounded border border-slate-200 px-2 text-[11px] font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-300"
                data-testid="agent-freeform-inspector-close"
                onClick={() => setInspectorOpen(false)}
              >
                Close
              </button>
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
      ) : null}
    </div>
  );
}

function FloatingPanelHeader({
  title,
  panel,
  pinned,
  onMovePointerDown,
  onPin,
}: {
  title: string;
  panel: FloatingPanelKey;
  pinned: boolean;
  onMovePointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onPin: () => void;
}) {
  return (
    <header className="flex h-9 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
      <span className="truncate text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
        {title}
      </span>
      <div className="flex items-center gap-1">
        <button type="button" className="cursor-grab rounded border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 active:cursor-grabbing dark:border-slate-800 dark:text-slate-300" data-testid={`agent-freeform-move-${panel}`} onPointerDown={onMovePointerDown}>
          Move
        </button>
        <button type="button" className="rounded border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-300" aria-pressed={pinned} data-testid={`agent-freeform-pin-${panel}`} onClick={(event) => { event.stopPropagation(); onPin(); }}>
          Pin
        </button>
      </div>
    </header>
  );
}

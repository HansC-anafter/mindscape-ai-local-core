import { useEffect, useMemo, useState } from 'react';
import { Lock, PlayCircle, RotateCcw, Unlock } from 'lucide-react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import type {
  HostRuntimeEvent,
  HostRuntimeSession,
  HostRuntimeStatus,
  SharedCliBridgeServiceStatus,
} from '@/lib/host-runtime-sessions';

import type { AgentFreeformLayoutState } from './agentFreeformLayoutModel';
import { mobilePanelOrder } from './agentFreeformLayoutValidator';
import { AgentFreeformDesktopWorkspace } from './AgentFreeformDesktopWorkspace';
import { AgentFreeformPanelContent } from './AgentFreeformPanelContent';
import { HostRuntimeStatusBadge } from './HostRuntimeStatusBadge';
import type { HostRuntimeGraphContext } from './hostRuntimeGraphContext';

function useCompactRunsCanvas(): boolean {
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const media = window.matchMedia('(max-width: 767px)');
    setCompact(media.matches);
    const handleChange = () => setCompact(media.matches);
    media.addEventListener?.('change', handleChange);
    return () => {
      media.removeEventListener?.('change', handleChange);
    };
  }, []);
  return compact;
}

function runtimeStatusFromEvent(event: HostRuntimeEvent): string | null {
  if (event.event_type === 'turn.failed') {
    return String(event.payload.reason || event.payload.status || 'failed');
  }
  if (event.event_type === 'turn.started') {
    return 'running';
  }
  if (event.event_type === 'turn.completed') {
    return 'completed';
  }
  if (event.event_type === 'session.ready') {
    return String(event.payload.status || 'ready');
  }
  if (event.event_type === 'session.closed') {
    return 'closed';
  }
  if (event.event_type === 'session.interrupted') {
    return 'interrupted';
  }
  if (event.event_type === 'connection_lost') {
    return 'bridge_disconnected';
  }
  return null;
}

function resolveEffectiveRuntimeStatus({
  error,
  events,
  isStarting,
  runtimeStatus,
  session,
}: {
  error: string | null;
  events: HostRuntimeEvent[];
  isStarting: boolean;
  runtimeStatus: HostRuntimeStatus | null;
  session: HostRuntimeSession | null;
}): string {
  if (error) {
    return error;
  }
  if (isStarting) {
    return 'running';
  }
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const status = runtimeStatusFromEvent(events[index]);
    if (status) {
      return status;
    }
  }
  if (session?.status && session.status !== 'ready') {
    return session.status;
  }
  if (runtimeStatus && !runtimeStatus.enabled) {
    return 'disabled';
  }
  if (runtimeStatus && runtimeStatus.total_bridges <= 0) {
    return 'bridge_unavailable';
  }
  if (session?.status === 'ready') {
    return 'ready';
  }
  return 'idle';
}

export function AgentFreeformCanvas({
  apiUrl,
  layout,
  events,
  session,
  runtimeStatus = null,
  bridgeService = null,
  meetingId,
  selectedObjectRef,
  graphContext,
  isStarting,
  error,
  isStartingBridge = false,
  compactLayout = false,
  onSubmitPrompt,
  onStartBridge,
  onSelectPanel,
  onResetLayout,
  onToggleLocked,
}: {
  apiUrl: string;
  layout: AgentFreeformLayoutState;
  events: HostRuntimeEvent[];
  session: HostRuntimeSession | null;
  runtimeStatus?: HostRuntimeStatus | null;
  bridgeService?: SharedCliBridgeServiceStatus | null;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
  graphContext?: HostRuntimeGraphContext | null;
  isStarting: boolean;
  isStartingBridge?: boolean;
  error: string | null;
  compactLayout?: boolean;
  onSubmitPrompt: (prompt: string) => void;
  onStartBridge?: () => void;
  onSelectPanel: (panelId: string) => void;
  onResetLayout: () => void;
  onToggleLocked: () => void;
}) {
  const viewportCompact = useCompactRunsCanvas();
  const compact = compactLayout || viewportCompact;
  const effectiveStatus = resolveEffectiveRuntimeStatus({
    error,
    events,
    isStarting,
    runtimeStatus,
    session,
  });
  const mobilePanels = mobilePanelOrder(layout.panels);
  const composerPanel = layout.panels.find((panel) => panel.id === 'composer' && !panel.collapsed) || null;
  const streamPanel = layout.panels.find((panel) =>
    (panel.type === 'timeline' || panel.type === 'model_feedback') && !panel.collapsed,
  ) || null;
  const dockPanels = useMemo(
    () => mobilePanelOrder(layout.panels).filter((panel) =>
      panel.id !== 'composer' &&
      panel.type !== 'timeline' &&
      panel.type !== 'model_feedback' &&
      !panel.collapsed,
    ),
    [layout.panels],
  );
  const canvasClassName = compact
    ? 'relative min-h-full overflow-visible bg-slate-100/90 p-3 pb-[calc(5rem+env(safe-area-inset-bottom,0px))] dark:bg-slate-950/90'
    : 'relative h-full min-h-[34rem] overflow-auto bg-slate-100/90 p-3 dark:bg-slate-950/90';
  const headerClassName = compact
    ? 'sticky top-0 z-40 mb-3 flex flex-col items-stretch gap-2 rounded-md border border-slate-200 bg-white/95 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/95'
    : 'sticky top-0 z-40 mb-3 flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white/95 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/95';
  const headerActionsClassName = compact
    ? 'flex min-w-0 items-center gap-2 overflow-x-auto overscroll-contain pb-1'
    : 'flex shrink-0 items-center gap-2';
  const bridgeStartVisible = effectiveStatus === 'bridge_unavailable' || bridgeService?.state === 'stopped';

  return (
    <section
      className={canvasClassName}
      data-testid="agent-freeform-canvas"
      data-layout-compact={compact}
      data-layout-locked={layout.locked}
    >
      <div className={headerClassName}>
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Host Runtime
          </div>
          <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
            Codex CLI run workspace
          </div>
        </div>
        <div className={headerActionsClassName}>
          <HostRuntimeStatusBadge status={effectiveStatus} />
          {bridgeStartVisible && onStartBridge ? (
            <button
              type="button"
              onClick={onStartBridge}
              disabled={isStartingBridge}
              className="inline-flex h-8 items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 text-xs font-semibold text-emerald-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"
              data-testid="host-runtime-start-bridge"
            >
              <PlayCircle className="h-3.5 w-3.5" aria-hidden="true" />
              {isStartingBridge ? 'Starting' : 'Start Bridge'}
            </button>
          ) : null}
          <button
            type="button"
            onClick={onToggleLocked}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-slate-200 px-2 text-xs font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300"
            data-testid="agent-freeform-lock-toggle"
          >
            {layout.locked ? <Lock className="h-3.5 w-3.5" aria-hidden="true" /> : <Unlock className="h-3.5 w-3.5" aria-hidden="true" />}
            {layout.locked ? 'Locked' : 'Lock'}
          </button>
          <button
            type="button"
            onClick={onResetLayout}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-slate-200 px-2 text-xs font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300"
            data-testid="agent-freeform-reset"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            Reset
          </button>
        </div>
      </div>

      {!compact ? (
        <AgentFreeformDesktopWorkspace
          apiUrl={apiUrl}
          layout={layout}
          events={events}
          session={session}
          effectiveStatus={effectiveStatus}
          meetingId={meetingId}
          selectedObjectRef={selectedObjectRef}
          graphContext={graphContext}
          isStarting={isStarting}
          composerPanel={composerPanel}
          streamPanel={streamPanel}
          dockPanels={dockPanels}
          onSubmitPrompt={onSubmitPrompt}
          onSelectPanel={onSelectPanel}
        />
      ) : null}

      {compact ? (
        <div className="space-y-3 pb-2" data-testid="agent-freeform-mobile-stack">
          {mobilePanels.map((panel) => panel.collapsed ? null : (
          <article
            key={panel.id}
            className="overflow-hidden rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
            data-testid={`agent-freeform-mobile-panel-${panel.id}`}
          >
            <header className="border-b border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:border-slate-800 dark:text-slate-400">
              {panel.title}
            </header>
            <div className="p-3">
              <AgentFreeformPanelContent
                panel={panel}
                apiUrl={apiUrl}
                events={events}
                session={session}
                effectiveStatus={effectiveStatus}
                meetingId={meetingId}
                selectedObjectRef={selectedObjectRef}
                graphContext={graphContext}
                isStarting={isStarting}
                onSubmitPrompt={onSubmitPrompt}
              />
            </div>
          </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

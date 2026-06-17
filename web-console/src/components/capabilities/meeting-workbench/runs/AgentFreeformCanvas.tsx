import { useEffect, useMemo, useState } from 'react';
import { Activity, CheckCircle2, GitBranch, Lock, MessageSquare, RotateCcw, Unlock, Wrench } from 'lucide-react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import type { HostRuntimeEvent, HostRuntimeSession, HostRuntimeStatus } from '@/lib/host-runtime-sessions';

import type { AgentFreeformLayoutState, AgentFreeformPanel } from './agentFreeformLayoutModel';
import { mobilePanelOrder } from './agentFreeformLayoutValidator';
import { HostRuntimeApprovalCard } from './HostRuntimeApprovalCard';
import { HostRuntimeComposer } from './HostRuntimeComposer';
import { HostRuntimeEventTimeline } from './HostRuntimeEventTimeline';
import { HostRuntimeGovernanceContextBar } from './HostRuntimeGovernanceContextBar';
import { HostRuntimeObjectContextBar } from './HostRuntimeObjectContextBar';
import { HostRuntimePatchCard } from './HostRuntimePatchCard';
import { HostRuntimeProvenanceCard } from './HostRuntimeProvenanceCard';
import { HostRuntimeStatusBadge } from './HostRuntimeStatusBadge';
import { HostRuntimeToolEventCard } from './HostRuntimeToolEventCard';
import type { HostRuntimeGraphContext } from './hostRuntimeGraphContext';

function zIndexForLayer(layer: AgentFreeformPanel['zLayer']): number {
  return layer === 'focus' ? 30 : layer === 'raised' ? 20 : 10;
}

function panelToolIcon(type: AgentFreeformPanel['type']) {
  switch (type) {
    case 'timeline':
    case 'model_feedback':
      return MessageSquare;
    case 'tool_calls':
      return Wrench;
    case 'approval_queue':
      return CheckCircle2;
    case 'object_context':
      return GitBranch;
    case 'trace_cards':
    case 'patch_files':
    case 'artifact_preview':
      return GitBranch;
    case 'resource_state':
    default:
      return Activity;
  }
}

function panelContent({
  panel,
  apiUrl,
  events,
  session,
  effectiveStatus,
  meetingId,
  selectedObjectRef,
  graphContext,
  isStarting,
  onSubmitPrompt,
}: {
  panel: AgentFreeformPanel;
  apiUrl: string;
  events: HostRuntimeEvent[];
  session: HostRuntimeSession | null;
  effectiveStatus: string;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
  graphContext?: HostRuntimeGraphContext | null;
  isStarting: boolean;
  onSubmitPrompt: (prompt: string) => void;
}) {
  switch (panel.type) {
    case 'composer':
      return <HostRuntimeComposer apiUrl={apiUrl} disabled={isStarting} onSubmit={onSubmitPrompt} />;
    case 'timeline':
    case 'model_feedback':
      return <HostRuntimeEventTimeline events={events} />;
    case 'tool_calls':
      return <HostRuntimeToolEventCard events={events} />;
    case 'approval_queue':
      return <HostRuntimeApprovalCard events={events} />;
    case 'patch_files':
      return <HostRuntimePatchCard events={events} />;
    case 'object_context':
      return (
        <HostRuntimeObjectContextBar
          meetingId={meetingId}
          selectedObjectRef={selectedObjectRef}
          graphContext={graphContext}
        />
      );
    case 'artifact_preview':
      return <HostRuntimeProvenanceCard events={events} />;
    case 'trace_cards':
      return (
        <div className="space-y-3">
          <HostRuntimeGovernanceContextBar events={events} />
          <HostRuntimeProvenanceCard events={events} />
        </div>
      );
    case 'resource_state':
      return (
        <div className="space-y-2 text-xs" data-testid="host-runtime-resource-state">
          <HostRuntimeStatusBadge status={effectiveStatus} />
          <div className="truncate font-mono text-slate-500 dark:text-slate-400">
            {session?.id || 'No session'}
          </div>
          <div className="text-slate-500 dark:text-slate-400">
            Stream-first; no transcript polling.
          </div>
        </div>
      );
    default:
      return <HostRuntimeEventTimeline events={events} />;
  }
}

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
  meetingId,
  selectedObjectRef,
  graphContext,
  isStarting,
  error,
  compactLayout = false,
  onSubmitPrompt,
  onSelectPanel,
  onResetLayout,
  onToggleLocked,
}: {
  apiUrl: string;
  layout: AgentFreeformLayoutState;
  events: HostRuntimeEvent[];
  session: HostRuntimeSession | null;
  runtimeStatus?: HostRuntimeStatus | null;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
  graphContext?: HostRuntimeGraphContext | null;
  isStarting: boolean;
  error: string | null;
  compactLayout?: boolean;
  onSubmitPrompt: (prompt: string) => void;
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
  const dockPanels = useMemo(
    () => mobilePanelOrder(layout.panels).filter((panel) => panel.id !== 'composer' && !panel.collapsed),
    [layout.panels],
  );
  const [activeDockPanelId, setActiveDockPanelId] = useState<string | null>(null);
  const activeDockPanel = dockPanels.find((panel) => panel.id === activeDockPanelId) || null;
  const canvasClassName = compact
    ? 'relative min-h-full overflow-visible bg-slate-100/90 p-3 pb-[calc(5rem+env(safe-area-inset-bottom,0px))] dark:bg-slate-950/90'
    : 'relative h-full min-h-[34rem] overflow-auto bg-slate-100/90 p-3 dark:bg-slate-950/90';
  const headerClassName = compact
    ? 'sticky top-0 z-40 mb-3 flex flex-col items-stretch gap-2 rounded-md border border-slate-200 bg-white/95 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/95'
    : 'sticky top-0 z-40 mb-3 flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white/95 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/95';
  const headerActionsClassName = compact
    ? 'flex min-w-0 items-center gap-2 overflow-x-auto overscroll-contain pb-1'
    : 'flex shrink-0 items-center gap-2';

  useEffect(() => {
    if (activeDockPanelId && !dockPanels.some((panel) => panel.id === activeDockPanelId)) {
      setActiveDockPanelId(null);
    }
  }, [activeDockPanelId, dockPanels]);

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
        <div className="flex min-h-0 h-[760px] gap-3" data-testid="agent-freeform-desktop-space">
          <div
            className="relative min-h-0 flex-1 overflow-auto rounded-md border border-slate-200 bg-white shadow-inner dark:border-slate-800 dark:bg-slate-950"
            data-testid="agent-freeform-mind-map-canvas"
          >
            <div
              className="relative h-full min-h-[760px] min-w-[1200px]"
              data-testid="agent-freeform-canvas-space"
              style={{
                backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(148, 163, 184, 0.28) 1px, transparent 0)',
                backgroundSize: '28px 28px',
              }}
            >
              {composerPanel ? (
                <article
                  className={`absolute flex min-h-0 flex-col overflow-hidden rounded-md border bg-white shadow-sm dark:bg-slate-950 ${
                    layout.selectedPanelId === composerPanel.id
                      ? 'border-blue-300 ring-2 ring-blue-100 dark:border-blue-700 dark:ring-blue-950'
                      : 'border-slate-200 dark:border-slate-800'
                  }`}
                  style={{
                    left: composerPanel.bounds.x,
                    bottom: 24,
                    width: composerPanel.bounds.width,
                    height: composerPanel.bounds.height,
                    zIndex: zIndexForLayer(composerPanel.zLayer),
                  }}
                  data-testid="agent-freeform-composer-dock"
                  data-panel-type={composerPanel.type}
                  onClick={() => onSelectPanel(composerPanel.id)}
                >
                  <header className="flex h-9 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
                    <span className="truncate text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                      {composerPanel.title}
                    </span>
                    {composerPanel.pinned ? <span className="text-[10px] font-semibold text-blue-600 dark:text-blue-300">PIN</span> : null}
                  </header>
                  <div className="min-h-0 flex-1 overflow-auto p-3">
                    {panelContent({ panel: composerPanel, apiUrl, events, session, effectiveStatus, meetingId, selectedObjectRef, graphContext, isStarting, onSubmitPrompt })}
                  </div>
                </article>
              ) : null}
            </div>
          </div>
          <aside
            className="flex min-h-0 shrink-0"
            data-testid="agent-freeform-runtime-tool-rail"
          >
            <div className="flex w-12 flex-col items-center gap-2 rounded-md border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
              {dockPanels.map((panel) => {
                const ToolIcon = panelToolIcon(panel.type);
                const active = activeDockPanelId === panel.id;
                return (
                  <button
                    key={panel.id}
                    type="button"
                    className={`inline-flex h-9 w-9 items-center justify-center rounded-md border text-slate-500 ${
                      active
                        ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/50 dark:text-blue-200'
                        : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400'
                    }`}
                    title={panel.title}
                    aria-label={panel.title}
                    aria-pressed={active}
                    data-testid={`agent-freeform-dock-button-${panel.id}`}
                    onClick={() => setActiveDockPanelId((current) => current === panel.id ? null : panel.id)}
                  >
                    <ToolIcon className="h-4 w-4" aria-hidden="true" />
                  </button>
                );
              })}
            </div>
            {activeDockPanel ? (
              <article
                className="ml-2 flex w-80 min-h-0 flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950"
                data-testid={`agent-freeform-side-panel-${activeDockPanel.id}`}
                data-panel-type={activeDockPanel.type}
              >
                <header className="flex h-10 shrink-0 items-center border-b border-slate-200 px-3 dark:border-slate-800">
                  <span className="truncate text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                    {activeDockPanel.title}
                  </span>
                </header>
                <div className="min-h-0 flex-1 overflow-auto p-3">
                  {panelContent({ panel: activeDockPanel, apiUrl, events, session, effectiveStatus, meetingId, selectedObjectRef, graphContext, isStarting, onSubmitPrompt })}
                </div>
              </article>
            ) : null}
          </aside>
        </div>
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
              {panelContent({ panel, apiUrl, events, session, effectiveStatus, meetingId, selectedObjectRef, graphContext, isStarting, onSubmitPrompt })}
            </div>
          </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

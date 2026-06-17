import { useEffect, useState } from 'react';
import { Lock, RotateCcw, Unlock } from 'lucide-react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import type { HostRuntimeEvent, HostRuntimeSession } from '@/lib/host-runtime-sessions';

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

function panelContent({
  panel,
  apiUrl,
  events,
  session,
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
          <HostRuntimeStatusBadge status={session?.status || 'idle'} />
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

export function AgentFreeformCanvas({
  apiUrl,
  layout,
  events,
  session,
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
  const panels = mobilePanelOrder(layout.panels);
  const canvasClassName = compact
    ? 'relative min-h-full overflow-visible bg-slate-100/90 p-3 pb-[calc(5rem+env(safe-area-inset-bottom,0px))] dark:bg-slate-950/90'
    : 'relative h-full min-h-[34rem] overflow-auto bg-slate-100/90 p-3 dark:bg-slate-950/90';
  const headerClassName = compact
    ? 'sticky top-0 z-40 mb-3 flex flex-col items-stretch gap-2 rounded-md border border-slate-200 bg-white/95 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/95'
    : 'sticky top-0 z-40 mb-3 flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white/95 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/95';
  const headerActionsClassName = compact
    ? 'flex min-w-0 items-center gap-2 overflow-x-auto overscroll-contain pb-1'
    : 'flex shrink-0 items-center gap-2';
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
          {error ? <HostRuntimeStatusBadge status={error} /> : <HostRuntimeStatusBadge status={session?.status || 'ready'} />}
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
        <div className="relative h-[760px] min-w-[1200px]" data-testid="agent-freeform-desktop-space">
          {layout.panels.map((panel) => panel.collapsed ? null : (
          <article
            key={panel.id}
            className={`absolute flex min-h-0 flex-col overflow-hidden rounded-md border bg-white shadow-sm dark:bg-slate-950 ${
              layout.selectedPanelId === panel.id
                ? 'border-blue-300 ring-2 ring-blue-100 dark:border-blue-700 dark:ring-blue-950'
                : 'border-slate-200 dark:border-slate-800'
            }`}
            style={{
              left: panel.bounds.x,
              top: panel.bounds.y,
              width: panel.bounds.width,
              height: panel.bounds.height,
              zIndex: zIndexForLayer(panel.zLayer),
            }}
            data-testid={`agent-freeform-panel-${panel.id}`}
            data-panel-type={panel.type}
            onClick={() => onSelectPanel(panel.id)}
          >
            <header className="flex h-9 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
              <span className="truncate text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                {panel.title}
              </span>
              {panel.pinned ? <span className="text-[10px] font-semibold text-blue-600 dark:text-blue-300">PIN</span> : null}
            </header>
            <div className="min-h-0 flex-1 overflow-auto p-3">
              {panelContent({ panel, apiUrl, events, session, meetingId, selectedObjectRef, graphContext, isStarting, onSubmitPrompt })}
            </div>
          </article>
          ))}
        </div>
      ) : null}

      {compact ? (
        <div className="space-y-3 pb-2" data-testid="agent-freeform-mobile-stack">
          {panels.map((panel) => panel.collapsed ? null : (
          <article
            key={panel.id}
            className="overflow-hidden rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
            data-testid={`agent-freeform-mobile-panel-${panel.id}`}
          >
            <header className="border-b border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:border-slate-800 dark:text-slate-400">
              {panel.title}
            </header>
            <div className="p-3">
              {panelContent({ panel, apiUrl, events, session, meetingId, selectedObjectRef, graphContext, isStarting, onSubmitPrompt })}
            </div>
          </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

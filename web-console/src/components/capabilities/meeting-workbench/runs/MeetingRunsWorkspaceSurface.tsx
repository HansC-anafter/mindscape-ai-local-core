import { useEffect, useRef } from 'react';

import type { AddressableGraphSelection, AddressableObjectRef } from '@/lib/addressable-object-layer';

import { AgentFreeformCanvas } from './AgentFreeformCanvas';
import type { AgentFreeformLayoutIntent } from './agentFreeformLayoutModel';
import { useAgentFreeformLayoutRuntime } from './useAgentFreeformLayoutRuntime';
import { useHostRuntimeRunSession } from './useHostRuntimeRunSession';

function isLayoutIntentPayload(value: unknown): value is AgentFreeformLayoutIntent {
  if (!value || typeof value !== 'object') return false;
  const payload = value as Record<string, unknown>;
  return typeof payload.operation === 'string' && typeof payload.panel_id === 'string';
}

export function MeetingRunsWorkspaceSurface({
  apiUrl,
  workspaceId,
  meetingId,
  selectedObjectRef,
  graphSelection,
  compactLayout = false,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
  graphSelection?: AddressableGraphSelection | null;
  compactLayout?: boolean;
}) {
  const runtime = useHostRuntimeRunSession({
    apiUrl,
    workspaceId,
    meetingId,
    selectedObjectRef,
    graphSelection,
  });
  const layout = useAgentFreeformLayoutRuntime();
  const appliedLayoutEventsRef = useRef<Set<string>>(new Set());
  const surfaceClassName = compactLayout
    ? 'min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain bg-slate-100 dark:bg-slate-950'
    : 'min-h-0 flex-1 overflow-hidden';

  useEffect(() => {
    runtime.events.forEach((event) => {
      const eventKey = `${event.seq ?? event.created_at}-${event.event_type}`;
      if (event.event_type !== 'layout.intent' || appliedLayoutEventsRef.current.has(eventKey)) {
        return;
      }
      if (isLayoutIntentPayload(event.payload)) {
        layout.applyIntent({
          ...event.payload,
          trace_refs: [
            ...(Array.isArray(event.payload.trace_refs) ? event.payload.trace_refs.map(String) : []),
            event.seq ? `host-runtime-event:${event.seq}` : event.event_type,
          ],
        });
        appliedLayoutEventsRef.current.add(eventKey);
      }
    });
  }, [layout, runtime.events]);

  return (
    <div
      className={surfaceClassName}
      data-testid="meeting-runs-workspace-surface"
      data-layout-compact={compactLayout}
      style={compactLayout ? { WebkitOverflowScrolling: 'touch' } : undefined}
    >
      <AgentFreeformCanvas
        apiUrl={apiUrl}
        layout={layout.state}
        events={runtime.events}
        session={runtime.session}
        runtimeStatus={runtime.status}
        meetingId={meetingId}
        selectedObjectRef={selectedObjectRef}
        graphContext={runtime.graphContext}
        isStarting={runtime.isStarting}
        error={runtime.error}
        compactLayout={compactLayout}
        onSubmitPrompt={runtime.submitPrompt}
        onSelectPanel={layout.selectPanel}
        onResetLayout={layout.resetLayout}
        onToggleLocked={layout.toggleLocked}
      />
    </div>
  );
}

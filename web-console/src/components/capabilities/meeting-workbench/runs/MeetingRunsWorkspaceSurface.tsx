import { useEffect, useRef } from 'react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';

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
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
}) {
  const runtime = useHostRuntimeRunSession({
    apiUrl,
    workspaceId,
    meetingId,
    selectedObjectRef,
  });
  const layout = useAgentFreeformLayoutRuntime();
  const appliedLayoutEventsRef = useRef<Set<string>>(new Set());

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
      className="min-h-0 flex-1 overflow-hidden"
      data-testid="meeting-runs-workspace-surface"
    >
      <AgentFreeformCanvas
        apiUrl={apiUrl}
        layout={layout.state}
        events={runtime.events}
        session={runtime.session}
        meetingId={meetingId}
        selectedObjectRef={selectedObjectRef}
        isStarting={runtime.isStarting}
        error={runtime.error}
        onSubmitPrompt={runtime.submitPrompt}
        onSelectPanel={layout.selectPanel}
        onResetLayout={layout.resetLayout}
        onToggleLocked={layout.toggleLocked}
      />
    </div>
  );
}

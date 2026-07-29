import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import type { HostRuntimeEvent, HostRuntimeSession } from '@/lib/host-runtime-sessions';

import type { AgentFreeformPanel } from './agentFreeformLayoutModel';
import { HostRuntimeApprovalCard } from './HostRuntimeApprovalCard';
import { HostRuntimeComposer } from './HostRuntimeComposer';
import { HostRuntimeEventTimeline } from './HostRuntimeEventTimeline';
import { HostRuntimeGovernanceContextBar } from './HostRuntimeGovernanceContextBar';
import { HostRuntimeObjectContextBar } from './HostRuntimeObjectContextBar';
import { HostRuntimePatchCard } from './HostRuntimePatchCard';
import { HostRuntimeProvenanceCard } from './HostRuntimeProvenanceCard';
import { HostRuntimeStatusBadge } from './HostRuntimeStatusBadge';
import { HostRuntimeSettlementCards } from './HostRuntimeSettlementCards';
import { HostRuntimeToolEventCard } from './HostRuntimeToolEventCard';
import type { HostRuntimeGraphContext } from './hostRuntimeGraphContext';

export function AgentFreeformPanelContent({
  panel,
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
}: {
  panel: AgentFreeformPanel;
  apiUrl: string;
  workspaceId?: string;
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
      return (
        <HostRuntimeComposer
          apiUrl={apiUrl}
          workspaceId={workspaceId}
          meetingId={meetingId}
          sessionId={session?.id || null}
          selectedObjectRef={selectedObjectRef}
          graphContext={graphContext}
          disabled={isStarting}
          onSubmit={onSubmitPrompt}
        />
      );
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
          <HostRuntimeSettlementCards apiUrl={apiUrl} workspaceId={session?.workspace_id || ''} />
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

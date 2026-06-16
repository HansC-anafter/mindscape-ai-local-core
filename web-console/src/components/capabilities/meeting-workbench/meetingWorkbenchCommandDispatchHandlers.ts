import type { Dispatch, SetStateAction } from 'react';

import type {
  AddressableObjectSummary,
  AddressableSelectionTarget,
} from '@/lib/addressable-object-layer';
import type { CompositionGraphCommandEnvelopeDraft } from '@/lib/composition-graph';
import { createMeetingCommandSubmitHandler, submitCompiledCompositionGraphCommand } from './meetingCommandSubmit';
import { dispatchMeetingCommandLedgerUpdated } from './meetingCommandEvents';
import { dispatchMeetingSessionNotification } from './meetingSessionNotifications';
import type {
  MeetingMentionItem,
  MeetingNode,
  MeetingPackTool,
  MeetingTranslate,
} from './meetingWorkbenchTypes';

export function createMeetingWorkbenchCommandDispatchHandlers({
  command,
  activeMeetingId,
  mentionItems,
  packTools,
  selectedPackToolId,
  effectiveSummary,
  effectiveSelection,
  selectedNode,
  objectTitle,
  capabilityCode,
  localTaskCount,
  apiUrl,
  workspaceId,
  setIsDispatching,
  setLocalTasks,
  setSelectedNodeId,
  setCommand,
  setIsConsoleOpen,
  setDispatchError,
  t,
}: {
  command: string;
  activeMeetingId: string;
  mentionItems: MeetingMentionItem[];
  packTools: MeetingPackTool[];
  selectedPackToolId: string;
  effectiveSummary: AddressableObjectSummary | null;
  effectiveSelection: AddressableSelectionTarget | null;
  selectedNode: MeetingNode | null;
  objectTitle: string;
  capabilityCode: string;
  localTaskCount: number;
  apiUrl: string;
  workspaceId: string;
  setIsDispatching: Dispatch<SetStateAction<boolean>>;
  setLocalTasks: Dispatch<SetStateAction<MeetingNode[]>>;
  setSelectedNodeId: Dispatch<SetStateAction<string>>;
  setCommand: Dispatch<SetStateAction<string>>;
  setIsConsoleOpen: Dispatch<SetStateAction<boolean>>;
  setDispatchError: Dispatch<SetStateAction<string | null>>;
  t: MeetingTranslate;
}) {
  async function handleCompiledGraphEnvelope(envelope: CompositionGraphCommandEnvelopeDraft) {
    if (!activeMeetingId) {
      return;
    }
    const nextNodeId = `task-${localTaskCount + 1}`;
    setLocalTasks((current) => [
      ...current,
      {
        id: nextNodeId,
        eyebrow: 'Composition Graph',
        title: envelope.intent_text,
        detail: t('directorGraphDispatching'),
        status: 'running',
        kind: 'run',
        lane: 'runs',
      },
    ]);
    setSelectedNodeId(nextNodeId);
    setDispatchError(null);
    setIsConsoleOpen(true);
    setIsDispatching(true);
    try {
      const commandLedger = await submitCompiledCompositionGraphCommand({
        apiUrl,
        workspaceId,
        meetingId: activeMeetingId,
        envelope,
      });
      dispatchMeetingCommandLedgerUpdated({
        workspaceId,
        meetingId: activeMeetingId,
        commandId: commandLedger.commandId,
        status: commandLedger.status,
      });
      dispatchMeetingSessionNotification({
        workspaceId,
        meetingId: activeMeetingId,
        commandId: commandLedger.commandId,
        tone: commandLedger.status === 'failed' ? 'error' : 'info',
        title: commandLedger.status === 'failed'
          ? t('meetingWorkbenchNotificationCommandFailed')
          : t('meetingWorkbenchNotificationCommandAccepted'),
        message: t('meetingWorkbenchNotificationAwaitingRuntime'),
      });
      setLocalTasks((current) =>
        current.map((node) =>
          node.id === nextNodeId
            ? {
                ...node,
                detail: t('meetingWorkbenchNotificationCommandAccepted'),
                status: commandLedger.status === 'failed' ? 'error' : 'ready',
                output: commandLedger.commandId,
              }
            : node,
        ),
      );
      setCommand('');
    } catch (cause) {
      const errorMessage = cause instanceof Error ? cause.message : 'Failed to dispatch compiled composition graph.';
      setDispatchError(errorMessage);
      setLocalTasks((current) =>
        current.map((node) =>
          node.id === nextNodeId
            ? {
                ...node,
                detail: errorMessage,
                status: 'error',
                output: errorMessage,
              }
            : node,
        ),
      );
    } finally {
      setIsDispatching(false);
    }
  }

  const handleSubmitCommand = createMeetingCommandSubmitHandler({
    command,
    activeMeetingId,
    mentionItems,
    packTools,
    selectedPackToolId,
    effectiveSummary,
    effectiveSelection,
    selectedNode,
    objectTitle,
    activeCapabilityCode: capabilityCode,
    localTaskCount,
    apiUrl,
    workspaceId,
    setIsDispatching,
    setLocalTasks,
    setSelectedNodeId,
    setCommand,
    setIsConsoleOpen,
    setDispatchError,
    t,
  });

  return { handleCompiledGraphEnvelope, handleSubmitCommand };
}

import type { Dispatch, SetStateAction } from 'react';

import type {
  AddressableGraphSelection,
  AddressableObjectSummary,
  AddressableSelectionTarget,
} from '@/lib/addressable-object-layer';
import type { CompositionGraphCommandEnvelopeDraft } from '@/lib/composition-graph';
import { submitMeetingCommandEnvelope } from './meetingCommandLedger';
import { dispatchMeetingCommandLedgerUpdated } from './meetingCommandEvents';
import { dispatchMeetingSessionNotification } from './meetingSessionNotifications';
import {
  buildMeetingCommandContextSnapshot,
  missingMeetingCommandContextMessage,
  type MeetingCommandIntentSource,
} from './meetingCommandContextSnapshot';
import type {
  MeetingMentionItem,
  MeetingMentionReference,
  MeetingNode,
  MeetingPackTool,
  MeetingTranslate,
} from './meetingWorkbenchTypes';
import type { MeetingCommandLedgerAcceptance } from './meetingCommandLedger';
import { isRecord, readString } from './meetingWorkbenchUtils';

export interface CreateMeetingCommandSubmitHandlerArgs {
  command: string;
  activeMeetingId: string | null;
  mentionItems: MeetingMentionItem[];
  packTools: MeetingPackTool[];
  selectedPackToolId: string;
  effectiveSummary: AddressableObjectSummary | null;
  effectiveSelection: AddressableSelectionTarget | null;
  graphSelection?: AddressableGraphSelection | null;
  selectedNode: MeetingNode | null;
  objectTitle: string;
  activeCapabilityCode: string;
  localTaskCount: number;
  apiUrl: string;
  workspaceId: string;
  setIsDispatching: (isDispatching: boolean) => void;
  setLocalTasks: Dispatch<SetStateAction<MeetingNode[]>>;
  setSelectedNodeId: (nodeId: string) => void;
  setCommand: (command: string) => void;
  setIsConsoleOpen: (isOpen: boolean) => void;
  setDispatchError: (error: string | null) => void;
  t: MeetingTranslate;
}

export interface SettleMeetingCommandAcceptanceArgs {
  commandLedger: MeetingCommandLedgerAcceptance;
  nextNodeId: string;
  selectedPackTool: MeetingPackTool | null;
  activeMeetingId: string;
  workspaceId: string;
  setLocalTasks: Dispatch<SetStateAction<MeetingNode[]>>;
  t: MeetingTranslate;
}

export function settleMeetingCommandAcceptance({
  commandLedger,
  nextNodeId,
  selectedPackTool,
  activeMeetingId,
  workspaceId,
  setLocalTasks,
  t,
}: SettleMeetingCommandAcceptanceArgs): void {
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
    tone: 'info',
    title: t('meetingWorkbenchNotificationCommandAccepted'),
    message: t('meetingWorkbenchNotificationAwaitingRuntime'),
  });
  const routeOwnedObjectAction = isRecord(commandLedger.dispatchResult?.object_action)
    ? commandLedger.dispatchResult.object_action
    : null;
  const routeOwnedObjectActionPlan = isRecord(commandLedger.dispatchResult?.object_action_plan)
    ? commandLedger.dispatchResult.object_action_plan
    : null;
  const routeOwnedPlaybook = isRecord(commandLedger.dispatchResult?.playbook)
    ? commandLedger.dispatchResult.playbook
    : null;
  const routeOwnedChat = isRecord(commandLedger.dispatchResult?.chat)
    ? commandLedger.dispatchResult.chat
    : null;
  const routeOwnedMeetingOrchestration = isRecord(
    commandLedger.dispatchResult?.meeting_orchestration,
  )
    ? commandLedger.dispatchResult.meeting_orchestration
    : null;
  const routeOwnedClientAction = isRecord(commandLedger.dispatchResult?.client_action)
    ? commandLedger.dispatchResult.client_action
    : null;
  if (routeOwnedMeetingOrchestration) {
    const taskId = readString(routeOwnedMeetingOrchestration.task_ir_id);
    const landingStatus = readString(
      routeOwnedMeetingOrchestration.artifact_landing_status,
    );
    const runnerStatus = readString(routeOwnedMeetingOrchestration.status);
    const output = [
      taskId ? `Task ID: ${taskId}` : '',
      landingStatus ? `Artifacts: ${landingStatus}` : '',
    ].filter(Boolean).join(' · ') || t('meetingWorkbenchNotificationAwaitingRuntime');
    setLocalTasks((current) =>
      current.map((node) =>
        node.id === nextNodeId
          ? {
              ...node,
              detail: runnerStatus === 'failed'
                ? t('meetingWorkbenchNotificationCommandFailed')
                : t('meetingWorkbenchNotificationCommandAccepted'),
              status: runnerStatus === 'failed' ? 'error' : 'ready',
              output,
            }
          : node,
      ),
    );
    window.dispatchEvent(new CustomEvent('workspace-task-updated'));
    dispatchMeetingSessionNotification({
      workspaceId,
      meetingId: activeMeetingId,
      commandId: commandLedger.commandId,
      tone: runnerStatus === 'failed' ? 'error' : 'info',
      title: runnerStatus === 'failed'
        ? t('meetingWorkbenchNotificationCommandFailed')
        : t('meetingWorkbenchNotificationCommandAccepted'),
      message: taskId || t('meetingWorkbenchNotificationAwaitingRuntime'),
    });
    return;
  }
  if (routeOwnedObjectAction) {
    setLocalTasks((current) =>
      current.map((node) =>
        node.id === nextNodeId
          ? {
              ...node,
              detail:
                readString(routeOwnedObjectAction.status) === 'succeeded'
                  ? t('meetingObjectActionCompleted')
                  : t('meetingObjectActionNoClosure'),
              status: readString(routeOwnedObjectAction.status) === 'failed'
                ? 'error'
                : 'ready',
              output: readString(routeOwnedObjectAction.execution_id)
                ? t('meetingExecutionId', {
                    executionId: readString(routeOwnedObjectAction.execution_id),
                  })
                : readString(routeOwnedObjectAction.task_id)
                  ? `Task ID: ${readString(routeOwnedObjectAction.task_id)}`
                  : t('meetingObjectActionInvoked'),
            }
          : node,
      ),
    );
    window.dispatchEvent(new CustomEvent('workspace-task-updated'));
    dispatchMeetingSessionNotification({
      workspaceId,
      meetingId: activeMeetingId,
      commandId: commandLedger.commandId,
      tone: readString(routeOwnedObjectAction.status) === 'failed'
        ? 'error'
        : 'success',
      title: readString(routeOwnedObjectAction.status) === 'failed'
        ? t('meetingWorkbenchNotificationCommandFailed')
        : t('meetingWorkbenchNotificationCommandCompleted'),
      message: readString(routeOwnedObjectAction.execution_id)
        || readString(routeOwnedObjectAction.task_id)
        || t('meetingWorkbenchNotificationInstructionDispatched'),
    });
    return;
  }
  if (routeOwnedObjectActionPlan) {
    const errors = Array.isArray(routeOwnedObjectActionPlan.errors)
      ? routeOwnedObjectActionPlan.errors
      : [];
    const firstError = errors.find(isRecord);
    const errorMessage = readString(firstError?.message);
    const planStatus = readString(routeOwnedObjectActionPlan.status);
    setLocalTasks((current) =>
      current.map((node) =>
        node.id === nextNodeId
          ? {
              ...node,
              detail: t('meetingObjectActionNoClosure'),
              status: planStatus === 'rejected' ? 'error' : 'ready',
              output: errorMessage || 'No executable object action was planned.',
            }
          : node,
      ),
    );
    window.dispatchEvent(new CustomEvent('workspace-task-updated'));
    dispatchMeetingSessionNotification({
      workspaceId,
      meetingId: activeMeetingId,
      commandId: commandLedger.commandId,
      tone: planStatus === 'rejected' ? 'error' : 'warning',
      title: planStatus === 'rejected'
        ? t('meetingWorkbenchNotificationCommandFailed')
        : t('meetingWorkbenchNotificationCommandAccepted'),
      message: errorMessage || t('meetingWorkbenchNotificationInstructionDispatched'),
    });
    return;
  }
  if (routeOwnedPlaybook) {
    const triggeredPlaybook = isRecord(routeOwnedPlaybook.triggered_playbook)
      ? routeOwnedPlaybook.triggered_playbook
      : null;
    const taskId =
      readString(routeOwnedPlaybook.task_id)
      || readString(triggeredPlaybook?.execution_id)
      || readString(triggeredPlaybook?.task_id);
    setLocalTasks((current) =>
      current.map((node) =>
        node.id === nextNodeId
          ? {
              ...node,
              detail:
                commandLedger.status === 'failed'
                  ? 'Pack tool dispatch failed.'
                  : `Accepted by ${selectedPackTool?.label || 'pack tool'}. Awaiting execution events.`,
              status: commandLedger.status === 'failed' ? 'error' : 'ready',
              output: taskId ? `Task ID: ${taskId}` : 'Instruction dispatched.',
            }
          : node,
      ),
    );
    window.dispatchEvent(new CustomEvent('workspace-task-updated'));
    dispatchMeetingSessionNotification({
      workspaceId,
      meetingId: activeMeetingId,
      commandId: commandLedger.commandId,
      tone: commandLedger.status === 'failed' ? 'error' : 'info',
      title: commandLedger.status === 'failed'
        ? t('meetingWorkbenchNotificationCommandFailed')
        : t('meetingWorkbenchNotificationCommandAccepted'),
      message: taskId || t('meetingWorkbenchNotificationAwaitingRuntime'),
    });
    return;
  }
  if (routeOwnedChat) {
    const taskId = readString(routeOwnedChat.task_id)
      || readString(routeOwnedChat.event_id);
    setLocalTasks((current) =>
      current.map((node) =>
        node.id === nextNodeId
          ? {
              ...node,
              detail: 'Accepted by the workspace runtime. Awaiting execution events.',
              status: 'ready',
              output: taskId ? `Task ID: ${taskId}` : 'Instruction dispatched.',
            }
          : node,
      ),
    );
    window.dispatchEvent(new CustomEvent('workspace-task-updated'));
    dispatchMeetingSessionNotification({
      workspaceId,
      meetingId: activeMeetingId,
      commandId: commandLedger.commandId,
      tone: 'info',
      title: t('meetingWorkbenchNotificationCommandAccepted'),
      message: taskId || t('meetingWorkbenchNotificationAwaitingRuntime'),
    });
    return;
  }
  if (routeOwnedClientAction) {
    const actionCode = readString(routeOwnedClientAction.action_code);
    setLocalTasks((current) =>
      current.map((node) =>
        node.id === nextNodeId
          ? {
              ...node,
              detail: t('meetingWorkbenchNotificationCommandAccepted'),
              status: 'ready',
              output: actionCode || t('meetingWorkbenchNotificationInstructionDispatched'),
            }
          : node,
      ),
    );
    window.dispatchEvent(new CustomEvent('workspace-task-updated'));
    return;
  }
  throw new Error('Meeting command route did not return a route-owned dispatch result.');
}

export function createMeetingCommandSubmitHandler({
  command,
  activeMeetingId,
  mentionItems,
  packTools,
  selectedPackToolId,
  effectiveSummary,
  effectiveSelection,
  graphSelection,
  selectedNode,
  objectTitle,
  activeCapabilityCode,
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
}: CreateMeetingCommandSubmitHandlerArgs) {
  return async function submitMeetingCommand(source: MeetingCommandIntentSource) {
    if (!activeMeetingId) {
      return;
    }
    const snapshot = buildMeetingCommandContextSnapshot({
      source,
      composerCommand: command,
      activeMeetingId,
      mentionItems,
      packTools,
      selectedPackToolId,
      effectiveSummary,
      effectiveSelection,
      selectedNode,
      objectTitle,
      activeCapabilityCode,
      graphSelection,
    });
    if (!snapshot) {
      return;
    }
    const missingContextMessage = missingMeetingCommandContextMessage(
      snapshot.missingRequiredRoles,
      t,
    );
    if (missingContextMessage) {
      setDispatchError(missingContextMessage);
      return;
    }
    const {
      actionParameters,
      command: trimmedCommand,
      mentionRefs: meetingMentionRefs,
      metadata,
      objectActionEntries,
      originSurface,
      selectedPackTool,
    } = snapshot;
    const nextNodeId = `task-${localTaskCount + 1}`;
    const nextNode: MeetingNode = {
      id: nextNodeId,
      eyebrow: selectedPackTool?.capabilityCode || 'Pack tool',
      title: trimmedCommand,
      detail: selectedPackTool
        ? `Dispatching through ${selectedPackTool.label}.`
        : 'Dispatching to the meeting thread.',
      status: 'running',
      kind: 'run',
      lane: 'runs',
    };
    setLocalTasks((current) => [...current, nextNode]);
    setSelectedNodeId(nextNodeId);
    setCommand('');
    setIsConsoleOpen(true);
    setDispatchError(null);
    setIsDispatching(true);

    try {
      const commandLedger = await submitMeetingCommandEnvelope({
        apiUrl,
        workspaceId,
        meetingId: activeMeetingId,
        command: trimmedCommand,
        originSurface,
        threadId: activeMeetingId,
        mentionRefs: meetingMentionRefs,
        objectActionEntries,
        selectedPackTool,
        actionParameters,
        metadata,
      });
      settleMeetingCommandAcceptance({
        commandLedger,
        nextNodeId,
        selectedPackTool,
        activeMeetingId,
        workspaceId,
        setLocalTasks,
        t,
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to dispatch meeting instruction.';
      setDispatchError(errorMessage);
      dispatchMeetingSessionNotification({
        workspaceId,
        meetingId: activeMeetingId,
        tone: 'error',
        title: t('meetingWorkbenchNotificationCommandFailed'),
        message: errorMessage,
      });
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
  };
}

function coerceCompiledMentionRefs(value: unknown): MeetingMentionReference[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is NonNullable<MeetingMentionItem['ref']> => isRecord(item) && typeof item.id === 'string' && typeof item.kind === 'string' && typeof item.token === 'string');
}

function coerceCompiledObjectActionEntries(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item) => isRecord(item) && typeof item.role === 'string' && isRecord(item.ref)) as Parameters<
    typeof submitMeetingCommandEnvelope
  >[0]['objectActionEntries'];
}

export async function submitCompiledCompositionGraphCommand({
  apiUrl,
  workspaceId,
  meetingId,
  envelope,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string;
  envelope: CompositionGraphCommandEnvelopeDraft;
}): Promise<MeetingCommandLedgerAcceptance> {
  const requestedAction = isRecord(envelope.requested_action) ? envelope.requested_action : null;
  const actionParameters = isRecord(requestedAction?.parameters) ? requestedAction.parameters : {};
  const compiledObjectEntries = [
    ...coerceCompiledObjectActionEntries(envelope.context_objects),
    ...coerceCompiledObjectActionEntries(actionParameters.object_action_entries),
  ];
  return submitMeetingCommandEnvelope({
    apiUrl,
    workspaceId,
    meetingId,
    command: envelope.intent_text,
    originSurface: 'meeting_workbench_director_graph',
    threadId: envelope.thread_id || meetingId,
    mentionRefs: coerceCompiledMentionRefs(envelope.meeting_mentions),
    objectActionEntries: compiledObjectEntries,
    selectedPackTool: null,
    requestedAction,
    actionParameters,
    metadata: {
      source_surface: 'meeting_workbench_director_graph',
      composition_graph_ref: isRecord(envelope.metadata?.composition_graph_ref)
        ? envelope.metadata.composition_graph_ref
        : null,
      selected_primary_pack: readString(envelope.metadata?.selected_primary_pack) || null,
    },
  });
}

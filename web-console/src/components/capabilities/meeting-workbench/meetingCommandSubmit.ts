import type { Dispatch, SetStateAction } from 'react';

import type {
  AddressableObjectSummary,
  AddressableSelectionTarget,
} from '@/lib/addressable-object-layer';
import {
  buildObjectActionPlanEntries,
  extractMentionReferences,
  isCharacterReference,
  isStoryboardReference,
  isStoryboardSceneReference,
} from './meetingMentions';
import { submitMeetingCommandEnvelope } from './meetingCommandLedger';
import { dispatchMeetingCommandLedgerUpdated } from './meetingCommandEvents';
import { dispatchMeetingSessionNotification } from './meetingSessionNotifications';
import {
  formatCommandContextRole,
  getGuidanceRequiredRoles,
  getMissingCommandContextRoles,
} from './meetingCommandValidation';
import type { MeetingMentionItem, MeetingNode, MeetingPackTool, MeetingTranslate } from './meetingWorkbenchTypes';
import { isRecord, readString } from './meetingWorkbenchUtils';

interface CreateMeetingCommandSubmitHandlerArgs {
  command: string;
  activeMeetingId: string | null;
  mentionItems: MeetingMentionItem[];
  packTools: MeetingPackTool[];
  selectedPackToolId: string;
  effectiveSummary: AddressableObjectSummary | null;
  effectiveSelection: AddressableSelectionTarget | null;
  selectedNode: MeetingNode | null;
  objectTitle: string;
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

export function createMeetingCommandSubmitHandler({
  command,
  activeMeetingId,
  mentionItems,
  packTools,
  selectedPackToolId,
  effectiveSummary,
  effectiveSelection,
  selectedNode,
  objectTitle,
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
  return async function handleSubmitCommand() {
    const trimmedCommand = command.trim();
    if (!trimmedCommand || !activeMeetingId) {
      return;
    }

    const meetingMentionRefs = extractMentionReferences(trimmedCommand, mentionItems);
    const explicitPackRef = meetingMentionRefs.find((ref) => ref.kind === 'pack');
    const selectedPackTool =
      (explicitPackRef
        ? packTools.find((tool) => {
            const qualifiedId = tool.capabilityCode ? `${tool.capabilityCode}.${tool.id}` : tool.id;
            return tool.id === explicitPackRef.id || qualifiedId === explicitPackRef.id;
          }) ?? null
        : null) ?? packTools.find((tool) => tool.id === selectedPackToolId) ?? null;
    const objectActionEntries = buildObjectActionPlanEntries(effectiveSummary?.ref, meetingMentionRefs);
    const missingRequiredRoles = getMissingCommandContextRoles(
      getGuidanceRequiredRoles(selectedNode),
      objectActionEntries,
    );
    if (missingRequiredRoles.length > 0) {
      setDispatchError(t('meetingWorkbenchCommandRequiredContextMissing', {
        value: missingRequiredRoles.map(formatCommandContextRole).join(', '),
      }));
      return;
    }
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
    const meetingActionParamsBase = {
      meeting_id: activeMeetingId,
      meeting_session_id: activeMeetingId,
      thread_id: activeMeetingId,
      meeting_command: trimmedCommand,
      selected_object_uri: effectiveSummary?.ref.uri,
      selected_object_title: objectTitle,
      selected_object_kind: effectiveSummary?.ref.object_kind || effectiveSelection?.objectKind,
      source_surface: effectiveSummary?.ref.source_surface || 'meeting_graph',
      meeting_mentions: meetingMentionRefs,
      target_storyboards: meetingMentionRefs.filter(isStoryboardReference),
      target_storyboard_scenes: meetingMentionRefs.filter(isStoryboardSceneReference),
      character_refs: meetingMentionRefs.filter(isCharacterReference),
      object_action_entries: objectActionEntries,
    };

    setLocalTasks((current) => [...current, nextNode]);
    setSelectedNodeId(nextNodeId);
    setCommand('');
    setIsConsoleOpen(true);
    setDispatchError(null);
    setIsDispatching(true);

    try {
      const originSurface = effectiveSummary?.ref.source_surface || 'meeting_workbench';
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
        actionParameters: meetingActionParamsBase,
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
                  status: readString(routeOwnedObjectAction.status) === 'failed' ? 'error' : 'ready',
                  output: readString(routeOwnedObjectAction.execution_id)
                    ? t('meetingExecutionId', { executionId: readString(routeOwnedObjectAction.execution_id) })
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
          tone: readString(routeOwnedObjectAction.status) === 'failed' ? 'error' : 'success',
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
          readString(routeOwnedPlaybook.task_id) ||
          readString(triggeredPlaybook?.execution_id) ||
          readString(triggeredPlaybook?.task_id);
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
        const taskId = readString(routeOwnedChat.task_id) || readString(routeOwnedChat.event_id);
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
      throw new Error('Meeting command route did not return a route-owned dispatch result.');
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

import { dispatchMeetingClientAction } from '@/lib/meeting-voice/meetingClientActionEvent';
import { submitVoiceTurn } from '@/lib/meeting-voice/voiceTurnClient';
import {
  workspaceInteractionRevision,
  type WorkspaceInteractionTarget,
} from '@/lib/workspace-interaction/workspaceInteractionTarget';

import type { MeetingCommandContextSnapshot } from './meetingCommandContextSnapshot';
import type { MeetingTranslate } from './meetingWorkbenchTypes';

export function createMeetingCommandVoiceTarget({
  apiUrl,
  workspaceId,
  meetingId,
  snapshot,
  onCommandAccepted,
  t,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string;
  snapshot: MeetingCommandContextSnapshot | null;
  onCommandAccepted: (input: {
    transcript: string;
    commandResponse: unknown;
    snapshot: MeetingCommandContextSnapshot;
  }) => void;
  t: MeetingTranslate;
}): WorkspaceInteractionTarget | null {
  if (!snapshot || snapshot.missingRequiredRoles.length > 0) {
    return null;
  }
  const frozenContext = {
    workspace_id: workspaceId,
    meeting_id: meetingId,
    command_context: snapshot.voiceCommandContext,
  };
  const handleCommandAccepted = ({
    transcript,
    commandResponse,
  }: {
    transcript: string;
    commandResponse: unknown;
  }) => {
    dispatchMeetingClientAction(commandResponse);
    onCommandAccepted({
      transcript,
      commandResponse,
      snapshot,
    });
  };

  return {
    targetId: `meeting_command:${workspaceId}:${meetingId}`,
    targetKind: 'meeting_command',
    targetLabel: t('workspaceVoiceTargetMeetingCommand'),
    revision: workspaceInteractionRevision('meeting_command', frozenContext),
    submissionPolicy: 'direct_submit',
    freezeContext: () => frozenContext,
    realtimeTransport: {
      kind: 'meeting_realtime',
      handleCommandAccepted,
    },
    submitVoiceTurn: async (turn) => {
      const response = await submitVoiceTurn({
        apiBase: apiUrl,
        workspaceId,
        meetingId,
        clientTurnId: turn.clientTurnId,
        audioBase64: turn.audioBase64,
        mimeType: turn.mimeType,
        language: turn.language,
        commandContext: snapshot.voiceCommandContext,
      });
      if (response.status === 'stt_unavailable') {
        throw new Error(response.reason || 'stt_unavailable');
      }
      const transcript = response.transcript?.trim() || '';
      if (!transcript) {
        return {
          status: 'ignored_empty_transcript',
          transcript: '',
        };
      }
      handleCommandAccepted({
        transcript,
        commandResponse: response.command_response,
      });
      return {
        status: 'submitted',
        transcript,
        commandResponse: response.command_response,
      };
    },
  };
}

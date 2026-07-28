import { dispatchMeetingClientAction } from '@/lib/meeting-voice/meetingClientActionEvent';
import {
  isAcceptedMeetingVoiceTurnResponse,
  submitVoiceTurn,
  type MeetingVoiceCommandContext,
} from '@/lib/meeting-voice/voiceTurnClient';
import {
  workspaceInteractionRevision,
  type WorkspaceInteractionTarget,
} from '@/lib/workspace-interaction/workspaceInteractionTarget';

export function createWorkspaceVoiceMeetingTarget({
  apiUrl,
  workspaceId,
  meetingId,
  commandContext,
  targetLabel,
  onCommandAccepted,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string;
  commandContext: MeetingVoiceCommandContext;
  targetLabel: string;
  onCommandAccepted?: (input: {
    transcript: string;
    commandResponse: unknown;
  }) => void;
}): WorkspaceInteractionTarget {
  const frozenContext = {
    workspace_id: workspaceId,
    meeting_id: meetingId,
    command_context: commandContext,
  };
  const handleCommandAccepted = ({
    transcript,
    commandResponse,
  }: {
    transcript: string;
    commandResponse: unknown;
  }) => {
    if (commandResponse === null || commandResponse === undefined) {
      return;
    }
    dispatchMeetingClientAction(commandResponse);
    onCommandAccepted?.({ transcript, commandResponse });
  };

  return {
    targetId: `meeting_command:${workspaceId}:${meetingId}`,
    targetKind: 'meeting_command',
    targetLabel,
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
        commandContext,
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
      const semanticResult = response.semantic_result;
      const answerText = semanticResult?.answer_text?.trim() || '';
      if (
        semanticResult?.outcome === 'grounded_answer'
        && answerText
      ) {
        return {
          status: 'answered',
          transcript,
          answerText,
          answerLanguage: semanticResult.answer_language,
          semanticResult,
        };
      }
      if (!isAcceptedMeetingVoiceTurnResponse(response)) {
        return {
          status: 'semantic_clarification',
          transcript,
          semanticResult,
        };
      }
      handleCommandAccepted({
        transcript,
        commandResponse: response.command_response,
      });
      return {
        status: 'submitted',
        transcript,
        semanticResult,
        commandResponse: response.command_response,
      };
    },
  };
}

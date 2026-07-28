import type { WorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';
import { createWorkspaceVoiceMeetingTarget } from '@/components/workspace/interaction/workspaceVoiceMeetingTarget';

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
  return createWorkspaceVoiceMeetingTarget({
    apiUrl,
    workspaceId,
    meetingId,
    commandContext: snapshot.voiceCommandContext,
    targetLabel: t('workspaceVoiceTargetMeetingCommand'),
    onCommandAccepted: ({
      transcript,
      commandResponse,
    }) => {
      onCommandAccepted({
        transcript,
        commandResponse,
        snapshot,
      });
    },
  });
}

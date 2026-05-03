import { MENTION_TOKEN_PATTERN } from './meetingWorkbenchConstants';
import type {
  MeetingMentionReference,
  MeetingObjectActionEntry,
  MeetingPackTool,
} from './meetingWorkbenchTypes';
import { postApiJson } from './meetingApi';
import { isRecord, readString } from './meetingWorkbenchUtils';

interface SubmitMeetingCommandEnvelopeArgs {
  apiUrl: string;
  workspaceId: string;
  meetingId: string;
  command: string;
  originSurface: string;
  threadId: string;
  mentionRefs: MeetingMentionReference[];
  objectActionEntries: MeetingObjectActionEntry[];
  selectedPackTool: MeetingPackTool | null;
  actionParameters?: Record<string, unknown>;
}

export interface MeetingCommandLedgerAcceptance {
  commandId: string;
  status: string;
  dispatchResult: Record<string, unknown> | null;
}

export function buildLedgerIntentText(
  command: string,
  objectActionEntries: MeetingObjectActionEntry[],
): string {
  MENTION_TOKEN_PATTERN.lastIndex = 0;
  const withoutUiMentions = command.replace(MENTION_TOKEN_PATTERN, (match, prefix: string) =>
    prefix && match.startsWith(prefix) ? prefix : ' ',
  );
  const normalized = withoutUiMentions.replace(/\s+/g, ' ').trim();
  const fallback =
    objectActionEntries.length > 0
      ? objectActionEntries.map((entry) => entry.ref.uri).join(' ')
      : 'Meeting command';
  return normalized || fallback;
}

export async function submitMeetingCommandEnvelope({
  apiUrl,
  workspaceId,
  meetingId,
  command,
  originSurface,
  threadId,
  mentionRefs,
  objectActionEntries,
  selectedPackTool,
  actionParameters = {},
}: SubmitMeetingCommandEnvelopeArgs): Promise<MeetingCommandLedgerAcceptance> {
  const hasSelectedGuidance = Boolean(
    actionParameters.selected_guidance_id ||
    actionParameters.selected_guidance_metadata ||
    actionParameters.selected_guidance_cards,
  );
  const dispatchMode =
    objectActionEntries.length > 0 || mentionRefs.length > 0 || selectedPackTool !== null || hasSelectedGuidance
      ? 'route_meeting_orchestration'
      : 'route_chat';
  const payload = await postApiJson(
    apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meetings/${encodeURIComponent(meetingId)}/commands`,
    {
      workspace_id: workspaceId,
      meeting_id: meetingId,
      origin_surface: originSurface || 'meeting_workbench',
      actor: 'user',
      intent_text: buildLedgerIntentText(command, objectActionEntries),
      context_objects: objectActionEntries,
      requested_action: selectedPackTool
        ? {
            verb: 'execute_playbook',
            pack_code: selectedPackTool.capabilityCode,
            playbook_code: selectedPackTool.id,
            write_mode: 'recommendation_only',
            parameters: {
              ...actionParameters,
              playbook_code: selectedPackTool.id,
              instruction: command,
              message: command,
            },
          }
        : null,
      write_mode: 'recommendation_only',
      thread_id: threadId,
      meeting_mentions: mentionRefs,
      metadata: {
        raw_intent_text: command,
        dispatch_mode: dispatchMode,
        selected_pack_tool_id: selectedPackTool?.id || null,
        selected_guidance_id: actionParameters.selected_guidance_id || null,
        selected_guidance_ids: actionParameters.selected_guidance_ids || null,
        selected_guidance_metadata: actionParameters.selected_guidance_metadata || null,
        selected_guidance_cards: actionParameters.selected_guidance_cards || null,
        selected_guidance_object_ref: actionParameters.selected_guidance_object_ref || null,
        action_parameters: actionParameters,
      },
    },
  );

  if (!isRecord(payload)) {
    throw new Error('Meeting command ledger returned an invalid response.');
  }
  const commandId = readString(payload.command_id);
  if (!commandId) {
    throw new Error('Meeting command ledger did not return a command id.');
  }
  return {
    commandId,
    status: readString(payload.status) || 'accepted',
    dispatchResult: isRecord(payload.dispatch_result) ? payload.dispatch_result : null,
  };
}

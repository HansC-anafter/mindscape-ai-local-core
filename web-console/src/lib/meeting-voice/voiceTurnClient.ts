export type MeetingVoiceTurnStatus =
  | 'transcribed_command_submitted'
  | 'semantic_clarification'
  | 'ignored_empty_transcript'
  | 'stt_unavailable';

export type WorkspaceVoiceSemanticTurnResult = {
  status:
    | 'command_submitted'
    | 'clarification_required'
    | 'reference_unresolved'
    | 'reference_ambiguous'
    | 'reference_count_exceeded'
    | 'interaction_unavailable'
    | 'stale_target';
  outcome:
    | 'grounded_material'
    | 'grounded_answer'
    | 'clarification'
    | 'not_applicable';
  decision_code: string;
  transcript: string;
  command_response?: unknown | null;
  answer_text?: string | null;
  answer_language?: string | null;
  client_action?: unknown | null;
};

export type MeetingVoiceTurnResponse = {
  status: MeetingVoiceTurnStatus;
  transcript?: string | null;
  language?: string | null;
  duration?: number | null;
  audio_byte_count?: number | null;
  command_response?: unknown | null;
  semantic_result?: WorkspaceVoiceSemanticTurnResult | null;
  reason?: string | null;
};

export type AcceptedMeetingVoiceTurnResponse = MeetingVoiceTurnResponse & {
  status: 'transcribed_command_submitted';
  command_response: NonNullable<unknown>;
};

export type MeetingVoiceCommandContext = {
  context_objects: unknown[];
  requested_action?: Record<string, unknown> | null;
  expected_outputs?: string[];
  write_mode?: 'recommendation_only' | 'proposal_only' | 'canonical_with_review' | 'staged';
  thread_id?: string | null;
  meeting_mentions?: object[];
  metadata?: Record<string, unknown>;
};

export type SubmitVoiceTurnInput = {
  apiBase: string;
  workspaceId: string;
  meetingId: string;
  clientTurnId: string;
  audioBase64: string;
  mimeType: string;
  language?: string;
  commandContext?: MeetingVoiceCommandContext;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

export function isAcceptedMeetingVoiceTurnResponse(
  response: MeetingVoiceTurnResponse,
): response is AcceptedMeetingVoiceTurnResponse {
  return (
    response.status === 'transcribed_command_submitted'
    && response.command_response !== null
    && response.command_response !== undefined
  );
}

export async function blobToBase64Audio(blob: Blob): Promise<string> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Failed to read audio blob'));
    reader.readAsDataURL(blob);
  });
  const [, payload = ''] = dataUrl.split(',', 2);
  return payload;
}

export async function submitVoiceTurn(
  input: SubmitVoiceTurnInput,
): Promise<MeetingVoiceTurnResponse> {
  const response = await fetch(
    `${trimTrailingSlash(input.apiBase)}/api/v1/workspaces/${encodeURIComponent(input.workspaceId)}/meetings/${encodeURIComponent(input.meetingId)}/voice-turns`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        client_turn_id: input.clientTurnId,
        audio_base64: input.audioBase64,
        mime_type: input.mimeType,
        language: input.language || 'auto',
        origin_surface: 'meeting_voice',
        command_context: input.commandContext,
      }),
    },
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const reason = body?.detail?.message || body?.detail?.reason || response.statusText;
    throw new Error(reason || 'Voice turn submission failed');
  }
  return body as MeetingVoiceTurnResponse;
}

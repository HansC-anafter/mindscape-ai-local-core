export interface WorkspaceSpeechToTextSegment {
  start?: number | null;
  end?: number | null;
  text?: string | null;
}

export interface WorkspaceSpeechToTextResponse {
  text: string;
  language?: string | null;
  duration?: number | null;
  segments?: WorkspaceSpeechToTextSegment[] | null;
}

export interface TranscribeWorkspaceAudioInput {
  apiUrl: string;
  audioBase64: string;
  language?: string;
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

export async function transcribeWorkspaceAudio(
  input: TranscribeWorkspaceAudioInput,
): Promise<WorkspaceSpeechToTextResponse> {
  const response = await fetch(
    `${trimTrailingSlash(input.apiUrl)}/api/v1/host/services/stt/transcribe`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        audio_base64: input.audioBase64,
        language: input.language || 'auto',
      }),
    },
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const reason = body?.detail?.message || body?.detail?.reason || response.statusText;
    throw new Error(reason || 'Workspace speech-to-text failed');
  }
  return body as WorkspaceSpeechToTextResponse;
}

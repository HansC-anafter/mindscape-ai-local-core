import { blobToBase64Audio } from '@/lib/meeting-voice/voiceTurnClient';

const WORKSPACE_VOICE_MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/wav',
] as const;

export function selectWorkspaceVoiceMimeType(): string | null {
  if (
    typeof MediaRecorder === 'undefined'
    || typeof MediaRecorder.isTypeSupported !== 'function'
  ) {
    return null;
  }
  return WORKSPACE_VOICE_MIME_CANDIDATES.find(
    (candidate) => MediaRecorder.isTypeSupported(candidate),
  ) || null;
}

export async function encodeWorkspaceVoiceBlob(blob: Blob): Promise<string> {
  return blobToBase64Audio(blob);
}

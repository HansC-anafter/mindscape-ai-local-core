import { blobToBase64Audio } from '@/lib/meeting-voice/voiceTurnClient';

export const WORKSPACE_VOICE_CHUNK_TIMESLICE_MS = 1000;

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

export type WorkspaceBoundedVoiceRecording = {
  audioBlob: Blob;
  mimeType: string;
};

export type WorkspaceBoundedVoiceRecorderHandle = {
  readonly state: RecordingState;
  stop: () => void;
  cancel: () => void;
};

type StartWorkspaceBoundedVoiceRecorderInput = {
  stream: MediaStream;
  mimeType: string;
  onComplete: (
    recording: WorkspaceBoundedVoiceRecording | null,
  ) => Promise<void> | void;
  onError: (error: Error) => void;
};

function mediaRecorderEventError(event: Event): Error {
  const error = (event as Event & { error?: DOMException }).error;
  if (!error) {
    return new Error('media_recorder_failed');
  }
  const normalized = new Error(error.message || 'media_recorder_failed');
  normalized.name = error.name || 'MediaRecorderError';
  return normalized;
}

export async function isWorkspaceVoiceBlobDecodable(blob: Blob): Promise<boolean> {
  if (blob.size === 0) {
    return false;
  }
  if (typeof OfflineAudioContext === 'undefined') {
    throw new Error('workspace_voice_audio_decoder_unavailable');
  }
  const decoder = new OfflineAudioContext(1, 1, 16000);
  try {
    const audio = await decoder.decodeAudioData(await blob.arrayBuffer());
    return audio.length > 0
      && Number.isFinite(audio.duration)
      && audio.duration > 0;
  } catch {
    return false;
  }
}

export function startWorkspaceBoundedVoiceRecorder(
  input: StartWorkspaceBoundedVoiceRecorderInput,
): WorkspaceBoundedVoiceRecorderHandle {
  const recorder = new MediaRecorder(input.stream, { mimeType: input.mimeType });
  const chunks: Blob[] = [];
  let cancelled = false;
  let settled = false;
  let tracksReleased = false;

  const releaseTracks = () => {
    if (tracksReleased) {
      return;
    }
    tracksReleased = true;
    input.stream.getTracks().forEach((track) => track.stop());
  };

  const fail = (error: Error) => {
    if (cancelled || settled) {
      return;
    }
    settled = true;
    releaseTracks();
    input.onError(error);
  };

  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      chunks.push(event.data);
    }
  };
  recorder.onerror = (event) => fail(mediaRecorderEventError(event));
  recorder.onstop = async () => {
    releaseTracks();
    if (cancelled || settled) {
      return;
    }
    try {
      const mimeType = recorder.mimeType || input.mimeType;
      const audioBlob = new Blob(chunks, { type: mimeType });
      const recording = await isWorkspaceVoiceBlobDecodable(audioBlob)
        ? { audioBlob, mimeType }
        : null;
      if (cancelled || settled) {
        return;
      }
      await input.onComplete(recording);
      settled = true;
    } catch (error) {
      fail(
        error instanceof Error
          ? error
          : new Error('bounded_voice_recording_failed'),
      );
    }
  };

  try {
    recorder.start(WORKSPACE_VOICE_CHUNK_TIMESLICE_MS);
  } catch (error) {
    releaseTracks();
    throw error;
  }

  return {
    get state() {
      return recorder.state;
    },
    stop: () => {
      if (recorder.state !== 'inactive') {
        recorder.stop();
      }
    },
    cancel: () => {
      cancelled = true;
      releaseTracks();
      if (recorder.state !== 'inactive') {
        recorder.stop();
      }
    },
  };
}

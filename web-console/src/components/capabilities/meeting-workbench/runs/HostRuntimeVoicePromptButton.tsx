import { useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';

import { blobToBase64Audio } from '@/lib/meeting-voice/voiceTurnClient';

import { transcribeHostRuntimeAudio } from './hostRuntimeSpeechToTextClient';

type HostRuntimeVoicePromptState =
  | 'idle'
  | 'recording'
  | 'submitting'
  | 'empty'
  | 'submitted'
  | 'error';

function getSupportedMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return null;
  }
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4;codecs=mp4a.40.2',
    'audio/mp4',
    'audio/wav',
  ];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) || null;
}

export function HostRuntimeVoicePromptButton({
  apiUrl,
  disabled = false,
  onTranscript,
}: {
  apiUrl: string;
  disabled?: boolean;
  onTranscript: (transcript: string) => void;
}) {
  const [state, setState] = useState<HostRuntimeVoicePromptState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [lastTranscript, setLastTranscript] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef<string | null>(null);

  const stopTracks = () => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  };

  const handleStop = () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      return;
    }
    recorder.stop();
  };

  const handleStart = async () => {
    setError(null);
    setLastTranscript(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setState('error');
      setError('microphone_unavailable');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      chunksRef.current = [];
      const mimeType = getSupportedMimeType();
      mimeTypeRef.current = mimeType;
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = async () => {
        stopTracks();
        const resolvedMimeType = recorder.mimeType || mimeTypeRef.current || 'audio/webm';
        const audioBlob = new Blob(chunksRef.current, { type: resolvedMimeType });
        if (audioBlob.size === 0) {
          setState('empty');
          return;
        }
        try {
          setState('submitting');
          const audioBase64 = await blobToBase64Audio(audioBlob);
          const response = await transcribeHostRuntimeAudio({
            apiUrl,
            audioBase64,
            language: 'auto',
          });
          const transcript = response.text.trim();
          if (!transcript) {
            setState('empty');
            return;
          }
          onTranscript(transcript);
          setLastTranscript(transcript);
          setState('submitted');
        } catch (err) {
          setState('error');
          setError(err instanceof Error ? err.message : 'host_runtime_voice_prompt_failed');
        }
      };
      recorder.start();
      setState('recording');
    } catch (err) {
      stopTracks();
      setState('error');
      setError(err instanceof Error ? err.message : 'microphone_permission_denied');
    }
  };

  const label = state === 'recording'
    ? 'Stop voice prompt'
    : state === 'submitting'
      ? 'Submitting voice prompt'
      : 'Start voice prompt';
  const title = lastTranscript ? `Transcript: ${lastTranscript}` : error || label;

  return (
    <button
      type="button"
      onClick={state === 'recording' ? handleStop : handleStart}
      disabled={disabled || state === 'submitting'}
      className={`inline-flex h-8 items-center gap-1 rounded-md border px-2 text-xs font-semibold transition-colors ${
        state === 'recording'
          ? 'border-red-200 bg-red-50 text-red-700 hover:bg-red-100 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200'
          : 'border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900'
      } disabled:cursor-not-allowed disabled:opacity-60`}
      aria-label={label}
      title={title}
      data-testid="host-runtime-voice-prompt-button"
      data-state={state}
    >
      {state === 'recording' ? (
        <Square className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <Mic className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      Voice
    </button>
  );
}

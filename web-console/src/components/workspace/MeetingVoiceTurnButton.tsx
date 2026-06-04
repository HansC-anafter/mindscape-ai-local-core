'use client';

import React, { useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';

import {
  blobToBase64Audio,
  submitVoiceTurn,
  type MeetingVoiceTurnResponse,
} from '@/lib/meeting-voice/voiceTurnClient';

type VoiceButtonState =
  | 'idle'
  | 'recording'
  | 'submitting'
  | 'submitted'
  | 'empty'
  | 'unavailable'
  | 'error';

interface MeetingVoiceTurnButtonProps {
  apiUrl: string;
  workspaceId: string;
  meetingId?: string | null;
  disabled?: boolean;
}

function buildClientTurnId(): string {
  return `voice_turn_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function getSupportedMimeType(): string {
  if (typeof MediaRecorder === 'undefined') {
    return 'audio/webm';
  }
  if (MediaRecorder.isTypeSupported?.('audio/webm;codecs=opus')) {
    return 'audio/webm;codecs=opus';
  }
  if (MediaRecorder.isTypeSupported?.('audio/webm')) {
    return 'audio/webm';
  }
  if (MediaRecorder.isTypeSupported?.('audio/wav')) {
    return 'audio/wav';
  }
  return 'audio/webm';
}

export function MeetingVoiceTurnButton({
  apiUrl,
  workspaceId,
  meetingId,
  disabled = false,
}: MeetingVoiceTurnButtonProps) {
  const [state, setState] = useState<VoiceButtonState>('idle');
  const [lastResult, setLastResult] = useState<MeetingVoiceTurnResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  if (!meetingId) {
    return null;
  }

  const stopTracks = () => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  };

  const handleStop = async () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      return;
    }
    recorder.stop();
  };

  const handleStart = async () => {
    setError(null);
    setLastResult(null);
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
      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = async () => {
        stopTracks();
        const audioBlob = new Blob(chunksRef.current, { type: mimeType });
        if (audioBlob.size === 0) {
          setState('empty');
          return;
        }
        try {
          setState('submitting');
          const audioBase64 = await blobToBase64Audio(audioBlob);
          const result = await submitVoiceTurn({
            apiBase: apiUrl,
            workspaceId,
            meetingId,
            clientTurnId: buildClientTurnId(),
            audioBase64,
            mimeType,
            language: 'auto',
          });
          setLastResult(result);
          if (result.status === 'ignored_empty_transcript') {
            setState('empty');
          } else if (result.status === 'stt_unavailable') {
            setState('unavailable');
          } else {
            setState('submitted');
          }
        } catch (err) {
          setState('error');
          setError(err instanceof Error ? err.message : 'voice_turn_failed');
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

  const isBusy = state === 'recording' || state === 'submitting';
  const label = state === 'recording'
    ? 'Stop voice turn'
    : state === 'submitting'
      ? 'Submitting voice turn'
      : 'Start voice turn';
  const resultTitle = lastResult?.transcript
    ? `Transcript: ${lastResult.transcript}`
    : error || label;

  return (
    <button
      type="button"
      onClick={state === 'recording' ? handleStop : handleStart}
      disabled={disabled || state === 'submitting'}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${state === 'recording'
        ? 'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-200'
        : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
        } disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400 dark:disabled:bg-gray-800 dark:disabled:text-gray-500`}
      aria-label={label}
      title={resultTitle}
      data-state={state}
      data-busy={isBusy ? 'true' : 'false'}
    >
      {state === 'recording' ? (
        <Square className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Mic className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  );
}

export default MeetingVoiceTurnButton;

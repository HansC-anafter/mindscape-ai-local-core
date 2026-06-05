'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Mic2, Radio, Square, X } from 'lucide-react';

import {
  openRealtimeVoiceSession,
  type RealtimeVoiceSessionEvent,
  type RealtimeVoiceSessionSocket,
} from '@/lib/meeting-voice/realtimeVoiceSessionClient';
import type { BrowserVadController } from '@/lib/meeting-voice/browserVadController';
import {
  fetchXttsHealth,
  VoicePlaybackQueue,
} from '@/lib/meeting-voice/voicePlaybackQueue';

type RealtimeButtonState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'transcribing'
  | 'interrupted'
  | 'closed'
  | 'speech_unavailable'
  | 'error';

interface RealtimeVoiceSessionButtonProps {
  apiUrl: string;
  workspaceId: string;
  meetingId?: string | null;
  disabled?: boolean;
}

function buildClientSessionId(): string {
  return `voice_session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function buildUtteranceId(): string {
  return `utt_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function RealtimeVoiceSessionButton({
  apiUrl,
  workspaceId,
  meetingId,
  disabled = false,
}: RealtimeVoiceSessionButtonProps) {
  const [state, setState] = useState<RealtimeButtonState>('idle');
  const [lastTranscript, setLastTranscript] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const socketRef = useRef<RealtimeVoiceSessionSocket | null>(null);
  const vadRef = useRef<BrowserVadController | null>(null);
  const playbackQueueRef = useRef<VoicePlaybackQueue | null>(null);

  useEffect(() => {
    playbackQueueRef.current = new VoicePlaybackQueue();
    return () => {
      playbackQueueRef.current?.interrupt();
      void vadRef.current?.destroy().catch(() => undefined);
      socketRef.current?.close();
    };
  }, []);

  if (!meetingId) {
    return null;
  }

  const handleEvent = (event: RealtimeVoiceSessionEvent) => {
    if (event.type === 'session_ready') {
      setState('listening');
      return;
    }
    if (event.type === 'transcript_candidate') {
      setState('transcribing');
      setLastTranscript(event.transcript || null);
      return;
    }
    if (event.type === 'transcript_final' || event.type === 'command_submitted') {
      setState('listening');
      setLastTranscript(event.transcript || lastTranscript);
      return;
    }
    if (event.type === 'speech_unavailable') {
      setState('speech_unavailable');
      setLastError(event.reason || 'speech_unavailable');
      return;
    }
    if (event.type === 'interrupted') {
      setState('interrupted');
      return;
    }
    if (event.type === 'cancelled') {
      setState('listening');
      return;
    }
    if (event.type === 'session_closed') {
      setState('closed');
      return;
    }
    if (event.type === 'session_error') {
      setLastError(event.reason || event.message || 'voice_session_error');
      setState(event.recoverable ? 'listening' : 'error');
    }
  };

  const closeSession = async () => {
    playbackQueueRef.current?.interrupt();
    await vadRef.current?.pause().catch(() => undefined);
    socketRef.current?.send({ type: 'session_close' });
    setState('closed');
  };

  const startSession = async () => {
    if (!meetingId || disabled || state === 'connecting') {
      return;
    }
    setState('connecting');
    setLastError(null);
    setLastTranscript(null);

    const xtts = await fetchXttsHealth(apiUrl);
    if (!xtts.available) {
      setLastError(xtts.reason || 'speech_unavailable');
    }

    const clientSessionId = buildClientSessionId();
    try {
      const socket = openRealtimeVoiceSession({
        apiBase: apiUrl,
        workspaceId,
        meetingId,
        clientSessionId,
        onOpen: async () => {
          socket.send({ type: 'session_start' });
          try {
            const { createBrowserVadController } = await import(
              '@/lib/meeting-voice/browserVadController'
            );
            const vad = await createBrowserVadController({
              onSpeechStart: () => setState('listening'),
              onSpeechEnd: async (window) => {
                const utteranceId = buildUtteranceId();
                setState('transcribing');
                socket.send({
                  type: 'audio_window',
                  utterance_id: utteranceId,
                  audio_base64: window.audioBase64,
                  mime_type: window.mimeType,
                  language: 'auto',
                  context_objects: [],
                  metadata: {},
                });
                socket.send({ type: 'utterance_end', utterance_id: utteranceId });
              },
              onError: (error) => {
                setLastError(error.message);
                setState('error');
              },
            });
            vadRef.current = vad;
            await vad.start();
          } catch (error) {
            setLastError(error instanceof Error ? error.message : 'vad_start_failed');
            setState('error');
            socket.close();
          }
        },
        onEvent: handleEvent,
        onError: (error) => {
          setLastError(error.message);
          setState('error');
        },
        onClose: () => {
          if (state !== 'error') {
            setState('closed');
          }
        },
      });
      socketRef.current = socket;
      if (!xtts.available) {
        setState('speech_unavailable');
      }
    } catch (error) {
      setLastError(error instanceof Error ? error.message : 'voice_session_failed');
      setState('error');
    }
  };

  const handleInterrupt = () => {
    playbackQueueRef.current?.interrupt();
    socketRef.current?.send({ type: 'interrupt' });
    setState('interrupted');
  };

  const active = ['connecting', 'listening', 'transcribing', 'speech_unavailable', 'interrupted'].includes(state);
  const title = lastTranscript
    ? `Transcript: ${lastTranscript}`
    : lastError || (active ? 'Realtime voice session active' : 'Start realtime voice session');

  return (
    <span className="inline-flex items-center gap-1" data-state={state}>
      <button
        type="button"
        onClick={active ? closeSession : startSession}
        disabled={disabled}
        className={`inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${active
          ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-900/40 dark:text-emerald-200'
          : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
          } disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400 dark:disabled:bg-gray-800 dark:disabled:text-gray-500`}
        aria-label={active ? 'Close realtime voice session' : 'Start realtime voice session'}
        title={title}
        data-state={state}
      >
        {active ? (
          <Radio className="h-4 w-4" aria-hidden="true" />
        ) : (
          <Mic2 className="h-4 w-4" aria-hidden="true" />
        )}
      </button>
      {active ? (
        <>
          <button
            type="button"
            onClick={handleInterrupt}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
            aria-label="Interrupt voice playback"
            title="Interrupt voice playback"
          >
            <Square className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={closeSession}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
            aria-label="Cancel realtime voice session"
            title="Cancel realtime voice session"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </>
      ) : null}
    </span>
  );
}

export default RealtimeVoiceSessionButton;

'use client';

import React from 'react';

import { useWorkspaceInteractionIngress } from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import {
  WorkspaceInteractionTargetError,
  type FrozenWorkspaceInteractionTarget,
} from '@/lib/workspace-interaction/workspaceInteractionTarget';

import {
  startMeetingRealtimeVoiceTransport,
  type MeetingRealtimeVoiceTransportHandle,
  type MeetingRealtimeVoiceTransportState,
} from './meetingRealtimeVoiceTransport';
import {
  encodeWorkspaceVoiceBlob,
  selectWorkspaceVoiceMimeType,
} from './workspaceBoundedVoiceTransport';

export type WorkspaceVoiceMode = 'bounded' | 'realtime';

export type WorkspaceVoiceState =
  | 'idle'
  | 'requesting_permission'
  | 'recording'
  | 'transcribing'
  | 'submitting'
  | 'draft_updated'
  | 'submitted'
  | 'answered'
  | 'semantic_clarification'
  | 'cancelled'
  | 'permission_denied'
  | 'unavailable'
  | 'empty'
  | 'stale_target'
  | 'realtime_connecting'
  | 'realtime_listening'
  | 'realtime_interrupted'
  | 'realtime_speech_unavailable'
  | 'realtime_answered'
  | 'realtime_clarification'
  | 'error';

function buildClientTurnId(): string {
  return `workspace_voice_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function realtimeState(
  state: MeetingRealtimeVoiceTransportState,
): WorkspaceVoiceState {
  if (state === 'connecting') return 'realtime_connecting';
  if (state === 'listening') return 'realtime_listening';
  if (state === 'transcribing') return 'transcribing';
  if (state === 'interrupted') return 'realtime_interrupted';
  if (state === 'speech_unavailable') return 'realtime_speech_unavailable';
  if (state === 'answered') return 'realtime_answered';
  if (state === 'clarification') return 'realtime_clarification';
  if (state === 'stale_target') return 'stale_target';
  if (state === 'error') return 'error';
  return 'idle';
}

export function useWorkspaceVoiceInteractionController(apiUrl: string) {
  const {
    activeTarget,
    assertFrozenTarget,
    freezeActiveTarget,
    submitFrozenVoiceTurn,
  } = useWorkspaceInteractionIngress();
  const [mode, setMode] = React.useState<WorkspaceVoiceMode>('bounded');
  const [state, setState] = React.useState<WorkspaceVoiceState>('idle');
  const [error, setError] = React.useState<string | null>(null);
  const [transcript, setTranscript] = React.useState<string | null>(null);
  const [answerText, setAnswerText] = React.useState<string | null>(null);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);
  const cancelledRef = React.useRef(false);
  const frozenRef = React.useRef<FrozenWorkspaceInteractionTarget | null>(null);
  const realtimeRef = React.useRef<MeetingRealtimeVoiceTransportHandle | null>(null);

  const stopTracks = React.useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const closeRealtime = React.useCallback(async () => {
    const current = realtimeRef.current;
    realtimeRef.current = null;
    await current?.close();
  }, []);

  const releaseResources = React.useCallback(() => {
    cancelledRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    stopTracks();
    void closeRealtime();
    frozenRef.current = null;
  }, [closeRealtime, stopTracks]);

  const cancel = React.useCallback(() => {
    releaseResources();
    setState('cancelled');
  }, [releaseResources]);

  React.useEffect(() => {
    if (!activeTarget?.realtimeTransport && mode === 'realtime') {
      setMode('bounded');
    }
  }, [activeTarget, mode]);

  React.useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        cancel();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      releaseResources();
    };
  }, [cancel, releaseResources]);

  React.useEffect(() => {
    const frozen = frozenRef.current;
    if (
      !frozen
      || (
        activeTarget
        && activeTarget.targetId === frozen.targetId
        && activeTarget.revision === frozen.targetRevision
      )
    ) {
      return;
    }
    releaseResources();
    setState('stale_target');
    setError('stale_target');
  }, [activeTarget, releaseResources]);

  const startBounded = React.useCallback(async () => {
    setError(null);
    setTranscript(null);
    setAnswerText(null);
    cancelledRef.current = false;
    let frozen: FrozenWorkspaceInteractionTarget;
    try {
      frozen = freezeActiveTarget();
      frozenRef.current = frozen;
    } catch (caught) {
      setState('unavailable');
      setError(caught instanceof Error ? caught.message : 'no_active_target');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      frozenRef.current = null;
      setState('unavailable');
      setError('microphone_unavailable');
      return;
    }
    const mimeType = selectWorkspaceVoiceMimeType();
    if (!mimeType) {
      frozenRef.current = null;
      setState('unavailable');
      setError('media_recorder_mime_unavailable');
      return;
    }
    try {
      setState('requesting_permission');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      try {
        assertFrozenTarget(frozen);
      } catch (caught) {
        stream.getTracks().forEach((track) => track.stop());
        frozenRef.current = null;
        setState('stale_target');
        setError(caught instanceof Error ? caught.message : 'stale_target');
        return;
      }
      if (cancelledRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        frozenRef.current = null;
        return;
      }
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = async () => {
        recorderRef.current = null;
        stopTracks();
        if (cancelledRef.current) {
          return;
        }
        const audioBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || mimeType,
        });
        if (audioBlob.size === 0) {
          setState('empty');
          return;
        }
        try {
          setState(
            frozen.submissionPolicy === 'direct_submit'
              ? 'submitting'
              : 'transcribing',
          );
          const result = await submitFrozenVoiceTurn(frozen, {
            clientTurnId: buildClientTurnId(),
            audioBase64: await encodeWorkspaceVoiceBlob(audioBlob),
            mimeType: recorder.mimeType || mimeType,
            language: 'auto',
          });
          setTranscript(result.transcript?.trim() || null);
          setAnswerText(result.answerText?.trim() || null);
          if (result.status === 'ignored_empty_transcript') {
            setState('empty');
          } else if (result.status === 'draft_updated') {
            setState('draft_updated');
          } else if (result.status === 'answered') {
            setState('answered');
          } else if (result.status === 'semantic_clarification') {
            setState('semantic_clarification');
          } else {
            setState('submitted');
          }
        } catch (caught) {
          if (
            caught instanceof WorkspaceInteractionTargetError
            && caught.code === 'stale_target'
          ) {
            setState('stale_target');
          } else {
            setState('error');
          }
          if (
            caught instanceof Error
            && (
              caught.message === 'stt_unavailable'
              || caught.message.startsWith('stt_')
            )
          ) {
            setState('unavailable');
          }
          setError(caught instanceof Error ? caught.message : 'voice_turn_failed');
        } finally {
          frozenRef.current = null;
        }
      };
      recorder.start();
      setState('recording');
    } catch (caught) {
      stopTracks();
      frozenRef.current = null;
      const permissionDenied = caught instanceof Error
        && ['NotAllowedError', 'SecurityError'].includes(caught.name);
      setState(permissionDenied ? 'permission_denied' : 'error');
      setError(caught instanceof Error ? caught.message : 'microphone_permission_denied');
    }
  }, [
    assertFrozenTarget,
    freezeActiveTarget,
    stopTracks,
    submitFrozenVoiceTurn,
  ]);

  const stopBounded = React.useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }
  }, []);

  const stopRealtime = React.useCallback(async () => {
    await closeRealtime();
    frozenRef.current = null;
    setState('idle');
  }, [closeRealtime]);

  const startRealtime = React.useCallback(async () => {
    if (!activeTarget?.realtimeTransport) {
      setState('unavailable');
      setError('realtime_unavailable');
      return;
    }
    setError(null);
    setTranscript(null);
    setAnswerText(null);
    try {
      const frozen = freezeActiveTarget();
      frozenRef.current = frozen;
      realtimeRef.current = await startMeetingRealtimeVoiceTransport({
        apiUrl,
        workspaceId: frozen.workspaceId,
        snapshot: frozen,
        assertCurrent: () => {
          assertFrozenTarget(frozen);
        },
        onState: (next) => setState(realtimeState(next)),
        onTranscript: setTranscript,
        onCommandAccepted: activeTarget.realtimeTransport.handleCommandAccepted,
        onSemanticResult: (result) => {
          setAnswerText(result.answer_text?.trim() || null);
        },
        onError: (caught) => setError(caught.message),
      });
    } catch (caught) {
      setState(
        caught instanceof WorkspaceInteractionTargetError
          ? 'stale_target'
          : 'error',
      );
      setError(caught instanceof Error ? caught.message : 'voice_session_failed');
    }
  }, [
    activeTarget,
    apiUrl,
    assertFrozenTarget,
    freezeActiveTarget,
  ]);

  const setVoiceMode = React.useCallback((next: WorkspaceVoiceMode) => {
    if (state !== 'idle' && state !== 'cancelled') {
      cancel();
    }
    setMode(next);
    setState('idle');
    setError(null);
    setTranscript(null);
    setAnswerText(null);
  }, [cancel, state]);

  return {
    activeTarget,
    mode,
    state,
    error,
    transcript,
    answerText,
    realtimeAvailable: Boolean(activeTarget?.realtimeTransport),
    setMode: setVoiceMode,
    start: mode === 'realtime' ? startRealtime : startBounded,
    stop: mode === 'realtime' ? stopRealtime : stopBounded,
    cancel,
    interruptRealtime: () => realtimeRef.current?.interrupt(),
  };
}

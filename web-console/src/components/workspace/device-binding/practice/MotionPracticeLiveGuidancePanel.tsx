'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FileText, Radio, Square, Volume2, VolumeX } from 'lucide-react';

import {
  buildMotionGuidanceWindowEvent,
  openMotionGuidanceSocket,
  type MotionGuidanceEvent,
  type MotionGuidanceSocket,
  type MotionGuidanceWindowEvent,
} from '@/lib/meeting-motion-guidance/motionGuidanceClient';
import {
  fetchXttsHealth,
  synthesizeXttsSpeech,
  VoicePlaybackQueue,
} from '@/lib/meeting-voice/voicePlaybackQueue';
import type { MotionPracticeLaunchResult } from '../motionPracticeLauncher';
import type { MotionPracticeLaunchInput } from '../motionPracticeLauncher';
import {
  closeMotionPracticeLiveGuidanceSession,
  type MotionPracticeClosureResult,
} from '../motionPracticeClosure';
import type { AppendMotionWindowResponse } from '@/lib/motion-analysis/motionWindowClient';
import type { MotionWindowSummary } from '@/lib/motion-analysis/livePoseWindow';

export type MotionPracticeWindowAppendEvent = {
  liveSessionId: string;
  response: AppendMotionWindowResponse;
  summary: MotionWindowSummary;
};

interface MotionPracticeLiveGuidancePanelProps {
  apiUrl: string;
  workspaceId: string;
  result: MotionPracticeLaunchResult | null;
  latestWindowAppend: MotionPracticeWindowAppendEvent | null;
  closureInput?: MotionPracticeLaunchInput | null;
}

type GuidanceConnectionState = 'idle' | 'connecting' | 'ready' | 'closed' | 'error';
type VoiceState = 'unknown' | 'available' | 'unavailable';
type ClosureState = 'idle' | 'closing' | 'rolling_up' | 'submitted' | 'error';

function toGuidanceWindowEvent(
  appendEvent: MotionPracticeWindowAppendEvent,
): MotionGuidanceWindowEvent | null {
  if (!appendEvent.response.accepted) {
    return null;
  }
  const motionWindowRef = appendEvent.response.motion_window_ref
    || appendEvent.summary.window_id;
  return buildMotionGuidanceWindowEvent({
    liveSessionId: appendEvent.liveSessionId,
    motionWindowRef,
    summary: appendEvent.summary,
  });
}

export function MotionPracticeLiveGuidancePanel({
  apiUrl,
  workspaceId,
  result,
  latestWindowAppend,
  closureInput = null,
}: MotionPracticeLiveGuidancePanelProps) {
  const [state, setState] = useState<GuidanceConnectionState>('idle');
  const [muted, setMuted] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>('unknown');
  const [lastCue, setLastCue] = useState<MotionGuidanceEvent | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [closureState, setClosureState] = useState<ClosureState>('idle');
  const [closureResult, setClosureResult] = useState<MotionPracticeClosureResult | null>(null);
  const socketRef = useRef<MotionGuidanceSocket | null>(null);
  const playbackRef = useRef(new VoicePlaybackQueue());
  const mutedRef = useRef(muted);
  const voiceStateRef = useRef<VoiceState>(voiceState);
  const sentWindowEventRef = useRef<string | null>(null);
  const closeRequestedRef = useRef(false);
  const closureStartedRef = useRef<string | null>(null);

  useEffect(() => {
    mutedRef.current = muted;
    if (muted) {
      playbackRef.current.interrupt();
    }
  }, [muted]);

  useEffect(() => {
    voiceStateRef.current = voiceState;
  }, [voiceState]);

  useEffect(() => {
    closeRequestedRef.current = false;
    closureStartedRef.current = null;
    setClosureState('idle');
    setClosureResult(null);
  }, [result?.liveSessionId, result?.practiceSessionId]);

  const speakCue = useCallback(async (event: MotionGuidanceEvent) => {
    if (!event.speakable || !event.cue_text || mutedRef.current) {
      return;
    }
    if (voiceStateRef.current !== 'available') {
      return;
    }
    try {
      const blob = await synthesizeXttsSpeech({
        apiBase: apiUrl,
        text: event.cue_text,
      });
      playbackRef.current.enqueue(blob);
    } catch (error) {
      setVoiceState('unavailable');
      setLastError(error instanceof Error ? error.message : 'xtts_synthesis_failed');
    }
  }, [apiUrl]);

  const runClosureSummary = useCallback(async () => {
    if (!result?.liveGuidanceEnabled || !result.liveSessionId || !closureInput) {
      setClosureState('error');
      setLastError('motion_practice_closure_input_missing');
      return;
    }
    const closureKey = `${result.practiceSessionId}:${result.liveSessionId}`;
    if (closureStartedRef.current === closureKey) {
      return;
    }
    closureStartedRef.current = closureKey;
    setClosureState('rolling_up');
    setLastError(null);
    try {
      const nextClosureResult = await closeMotionPracticeLiveGuidanceSession({
        input: closureInput,
        result,
      });
      setClosureResult(nextClosureResult);
      setClosureState('submitted');
    } catch (error) {
      setClosureState('error');
      setLastError(error instanceof Error ? error.message : 'motion_practice_closure_failed');
    }
  }, [closureInput, result]);

  const handleGuidanceEvent = useCallback((event: MotionGuidanceEvent) => {
    if (event.type === 'session_ready') {
      setState('ready');
      void fetchXttsHealth(apiUrl).then((health) => {
        setVoiceState(health.available ? 'available' : 'unavailable');
        if (!health.available) {
          setLastError(health.reason || 'xtts_unavailable');
        }
      });
      return;
    }
    if (event.type === 'session_closed') {
      setState('closed');
      if (closeRequestedRef.current) {
        void runClosureSummary();
      }
      return;
    }
    if (event.type === 'session_error') {
      setState('error');
      setLastError(event.reason || event.message || 'motion_guidance_error');
      return;
    }
    if (event.type === 'interrupted') {
      playbackRef.current.interrupt();
    }
    if (event.type === 'guidance_cue' || event.type === 'guidance_suppressed') {
      setLastCue(event);
      void speakCue(event);
    }
  }, [apiUrl, runClosureSummary, speakCue]);

  useEffect(() => {
    if (!result?.liveGuidanceEnabled || !result.liveSessionId || !result.practiceSessionId) {
      socketRef.current?.close();
      socketRef.current = null;
      setState('idle');
      return undefined;
    }
    setState('connecting');
    setLastError(null);
    const socket = openMotionGuidanceSocket({
      apiBase: apiUrl,
      workspaceId,
      meetingId: result.meetingId,
      practiceSessionId: result.practiceSessionId,
      liveSessionId: result.liveSessionId,
      onEvent: handleGuidanceEvent,
      onError: (error) => {
        setLastError(error.message);
        setState('error');
      },
      onClose: () => setState((current) => (current === 'error' ? 'error' : 'closed')),
    });
    socketRef.current = socket;
    return () => {
      socket.close();
      playbackRef.current.interrupt();
      socketRef.current = null;
    };
  }, [apiUrl, handleGuidanceEvent, result, workspaceId]);

  useEffect(() => {
    if (!result?.liveGuidanceEnabled || !latestWindowAppend || !socketRef.current) {
      return;
    }
    if (latestWindowAppend.liveSessionId !== result.liveSessionId) {
      return;
    }
    const guidanceWindow = toGuidanceWindowEvent(latestWindowAppend);
    if (!guidanceWindow || sentWindowEventRef.current === guidanceWindow.eventId) {
      return;
    }
    sentWindowEventRef.current = guidanceWindow.eventId;
    socketRef.current.send({
      type: 'motion_window',
      event_id: guidanceWindow.eventId,
      live_session_id: guidanceWindow.liveSessionId,
      motion_window_ref: guidanceWindow.motionWindowRef,
      confidence: guidanceWindow.confidence,
      top_findings: guidanceWindow.findings,
      findings: guidanceWindow.findings,
      metadata: {
        source: 'workspace_motion_source_rail',
        summary_window_id: guidanceWindow.summary.window_id,
      },
    });
  }, [latestWindowAppend, result]);

  const interrupt = () => {
    playbackRef.current.interrupt();
    socketRef.current?.send({ type: 'interrupt', event_id: `${result?.practiceSessionId || 'practice'}:interrupt` });
  };

  const closeGuidance = () => {
    if (!result?.practiceSessionId || !socketRef.current) {
      setClosureState('error');
      setLastError('motion_guidance_socket_not_ready');
      return;
    }
    closeRequestedRef.current = true;
    setClosureState('closing');
    setLastError(null);
    socketRef.current.send({
      type: 'session_close',
      event_id: `${result.practiceSessionId}:session_close`,
    });
  };

  if (!result?.liveGuidanceEnabled) {
    return null;
  }

  return (
    <div className="space-y-2 rounded-md border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-100">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-semibold">
          <Radio className="h-4 w-4" aria-hidden="true" />
          Live guidance
        </div>
        <div className="rounded border border-sky-200 px-2 py-0.5 font-mono dark:border-sky-800" data-testid="motion-guidance-state">
          {state}
        </div>
      </div>

      {lastCue ? (
        <div className="rounded border border-sky-200 bg-white p-2 dark:border-sky-800 dark:bg-gray-950" data-testid="motion-guidance-last-cue">
          <div className="text-[11px] uppercase tracking-normal text-sky-600 dark:text-sky-300">
            {lastCue.type === 'guidance_suppressed' ? lastCue.reason : lastCue.cue_priority}
          </div>
          <div>{lastCue.cue_text || lastCue.message || 'Waiting for the next compact motion cue.'}</div>
        </div>
      ) : (
        <div className="rounded border border-sky-200 bg-white p-2 dark:border-sky-800 dark:bg-gray-950">
          Waiting for compact motion windows.
        </div>
      )}

      {lastError ? (
        <div className="rounded border border-amber-200 bg-amber-50 p-2 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200" data-testid="motion-guidance-error">
          {lastError}
        </div>
      ) : null}

      {closureState !== 'idle' ? (
        <div className="rounded border border-sky-200 bg-white p-2 dark:border-sky-800 dark:bg-gray-950" data-testid="motion-guidance-closure-state">
          <div className="text-[11px] uppercase tracking-normal text-sky-600 dark:text-sky-300">
            session close
          </div>
          <div>
            {closureState === 'submitted'
              ? `rollup ${closureResult?.rollup.motion_rollup_ref || 'emitted'} · command ${closureResult?.command.commandId || 'accepted'}`
              : closureState}
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-2">
        <button
          type="button"
          onClick={() => setMuted((value) => !value)}
          className="inline-flex items-center justify-center gap-1 rounded-md border border-sky-300 bg-white px-2 py-1.5 font-medium hover:bg-sky-100 dark:border-sky-800 dark:bg-gray-950 dark:hover:bg-sky-950"
          data-testid="motion-guidance-mute-button"
        >
          {muted ? <VolumeX className="h-3.5 w-3.5" aria-hidden="true" /> : <Volume2 className="h-3.5 w-3.5" aria-hidden="true" />}
          {muted ? 'Muted' : voiceState}
        </button>
        <button
          type="button"
          onClick={interrupt}
          className="inline-flex items-center justify-center gap-1 rounded-md border border-sky-300 bg-white px-2 py-1.5 font-medium hover:bg-sky-100 dark:border-sky-800 dark:bg-gray-950 dark:hover:bg-sky-950"
          data-testid="motion-guidance-interrupt-button"
        >
          <Square className="h-3.5 w-3.5" aria-hidden="true" />
          Interrupt
        </button>
        <button
          type="button"
          onClick={closeGuidance}
          disabled={!closureInput || closureState === 'closing' || closureState === 'rolling_up' || closureState === 'submitted'}
          className="inline-flex items-center justify-center gap-1 rounded-md border border-sky-300 bg-white px-2 py-1.5 font-medium hover:bg-sky-100 disabled:cursor-not-allowed disabled:bg-sky-100 disabled:text-sky-400 dark:border-sky-800 dark:bg-gray-950 dark:hover:bg-sky-950 dark:disabled:bg-sky-950/30"
          data-testid="motion-guidance-close-button"
          title="End guidance and submit a compact practice summary"
        >
          <FileText className="h-3.5 w-3.5" aria-hidden="true" />
          End
        </button>
      </div>
    </div>
  );
}

export default MotionPracticeLiveGuidancePanel;

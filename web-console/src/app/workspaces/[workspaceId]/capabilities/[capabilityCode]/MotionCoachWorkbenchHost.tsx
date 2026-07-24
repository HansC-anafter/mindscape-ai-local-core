'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import {
  CaptureSourceBridgeProvider,
  type CaptureSourceReferenceLessonState,
  useCaptureSourceBridge,
  useOptionalCaptureSourceBridge,
} from '@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider';
import { PhoneSourcePreview } from '@/components/workspace/device-binding/PhoneSourcePreview';
import type { MotionPracticeClosureResult } from '@/components/workspace/device-binding/motionPracticeClosure';
import {
  launchMotionPractice,
  type MotionPracticeLaunchInput,
  type MotionPracticeLaunchResult,
  type MotionPracticeCoachPack,
} from '@/components/workspace/device-binding/motionPracticeLauncher';
import type { MotionWindowAppendEvent } from '@/components/workspace/device-binding/motionWindowAppendEvent';
import {
  buildInstructionRefsFromLessonHandoff,
  buildInstructionSourceStateFromLessonHandoff,
  parseMotionPracticeLessonHandoff,
} from '@/components/workspace/device-binding/practice/motionPracticeLessonHandoff';
import { buildMotionPracticeLessonHandoffFromGraphSelection } from '@/components/workspace/device-binding/practice/motionPracticeGraphSelection';
import {
  confirmMotionPracticeReferencePlayback,
  prepareMotionPracticeReferencePlayback,
  type MotionPracticeReferencePlaybackPlan,
} from '@/components/workspace/device-binding/practice/motionPracticeReferencePlayback';
import {
  subscribeMeetingClientActions,
} from '@/lib/meeting-voice/meetingClientActionEvent';
import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import type { CapabilityTaskConfirmationBridge } from '@/types/capability-workbench';
import { requestPackScopeToolClose } from '@/components/capabilities/workbench/packScopeToolEvents';
import { useWorkspaceGroupOptional } from '@/contexts/WorkspaceGroupContext';
import {
  buildDancePracticeWorkbenchState,
  buildYogaPracticeWorkbenchState,
  type MotionCoachCapabilityCode,
} from './motionCoachWorkbenchState';

interface MotionCoachWorkbenchHostProps {
  workspaceId: string;
  apiUrl: string;
  capabilityCode: MotionCoachCapabilityCode;
  Component: React.ComponentType<any>;
  aolHost: any;
  surfacePath: readonly string[];
  taskConfirmation?: CapabilityTaskConfirmationBridge;
}

const MAX_WINDOW_EVENTS = 60;
const MAX_RETAINED_PLAYBACK_LAUNCHES = 64;
const playbackLaunchesByConfirmation = new Map<
  string,
  Promise<MotionPracticeLaunchResult>
>();
const ATTACHED_RECEIVER_STATES = new Set([
  'starting',
  'waiting_source',
  'receiving',
  'analyzing',
  'degraded',
  'stopping',
]);

function hasAttachedMediaReceiver(session: DeviceSessionEntry): boolean {
  return Boolean(
    session.media_session_id
    && ATTACHED_RECEIVER_STATES.has(session.media_session_state || ''),
  );
}

function buildAttachedMotionPracticeResult(
  session: DeviceSessionEntry,
  coachPack: MotionPracticeCoachPack,
): MotionPracticeLaunchResult | null {
  const handoff = session.media_analysis_handoff;
  if (
    !handoff
    || handoff.coach_pack !== coachPack
    || !handoff.live_motion_session_id
    || !handoff.meeting_session_id
    || !handoff.practice_session_id
  ) {
    return null;
  }
  return {
    meetingId: handoff.meeting_session_id,
    commandId: null,
    playbookExecutionId: null,
    liveSessionId: handoff.live_motion_session_id,
    sourceSessionId: session.session_id,
    practiceSessionId: handoff.practice_session_id,
    liveGuidanceEnabled: handoff.practice_mode === 'live_guidance',
    coachPack,
    practiceMode: handoff.practice_mode,
    status: 'active',
  };
}

function resolveCoachPack(capabilityCode: MotionCoachCapabilityCode): MotionPracticeCoachPack {
  return capabilityCode === 'dance_motion_coach' ? 'dance_motion_coach' : 'yogacoach';
}

function launchMotionPracticeOnce(
  launchKey: string,
  input: MotionPracticeLaunchInput,
): Promise<MotionPracticeLaunchResult> {
  const existing = playbackLaunchesByConfirmation.get(launchKey);
  if (existing) {
    return existing;
  }
  const pending = launchMotionPractice(input);
  playbackLaunchesByConfirmation.set(launchKey, pending);
  while (playbackLaunchesByConfirmation.size > MAX_RETAINED_PLAYBACK_LAUNCHES) {
    const oldestKey = playbackLaunchesByConfirmation.keys().next().value;
    if (typeof oldestKey !== 'string') {
      break;
    }
    playbackLaunchesByConfirmation.delete(oldestKey);
  }
  return pending;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

function readNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function readRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function buildReferenceLessonDeviceState(
  workbenchState: Record<string, unknown>,
): CaptureSourceReferenceLessonState | null {
  const lessonState = isRecord(workbenchState.reference_lesson_state)
    ? workbenchState.reference_lesson_state
    : null;
  if (!lessonState) {
    return null;
  }
  const lessonId = readString(lessonState.lesson_id);
  if (!lessonId || lessonId === 'lesson_pending') {
    return null;
  }
  const activeId = readString(lessonState.activeChapterId) || readString(lessonState.activePhraseId);
  const entries = readRecordArray(lessonState.chapters).length
    ? readRecordArray(lessonState.chapters)
    : readRecordArray(lessonState.phrases);
  const activeEntry = entries.find((entry) => readString(entry.id) === activeId) || entries[0] || null;
  const focusCue = readString(activeEntry?.focus)
    || readString(activeEntry?.teacherCue)
    || readString(activeEntry?.rhythmFocus)
    || readString(activeEntry?.styleCue);
  return {
    chapter_ref: activeId || readString(activeEntry?.id),
    title: readString(activeEntry?.title) || readString(lessonState.title),
    timestamp_ms: readNumber(activeEntry?.startMs),
    poster_ref: readString(activeEntry?.thumbnailUrl) || readString(lessonState.thumbnailUrl),
    focus_cue: focusCue,
  };
}

function MotionCoachWorkbenchHostContent({
  workspaceId,
  apiUrl,
  capabilityCode,
  Component,
  aolHost,
  surfacePath,
  taskConfirmation,
}: MotionCoachWorkbenchHostProps) {
  const workspaceGroup = useWorkspaceGroupOptional();
  const searchParams = useSearchParams();
  const captureSourceBridge = useCaptureSourceBridge();
  const { sessions, referenceLessonState } = captureSourceBridge;
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [practiceResult, setPracticeResult] = useState<MotionPracticeLaunchResult | null>(null);
  const [launchInput, setLaunchInput] = useState<MotionPracticeLaunchInput | null>(null);
  const [motionWindowEvents, setMotionWindowEvents] = useState<MotionWindowAppendEvent[]>([]);
  const [closureResult, setClosureResult] = useState<MotionPracticeClosureResult | null>(null);
  const [agentLessonHandoff, setAgentLessonHandoff] = useState<ReturnType<typeof parseMotionPracticeLessonHandoff>>(null);
  const [referencePlaybackPlan, setReferencePlaybackPlan] = useState<MotionPracticeReferencePlaybackPlan | null>(null);
  const publishedReferenceLessonKeyRef = useRef('');
  const previousSessionCountRef = useRef(sessions.length);
  const recoveryInFlightRef = useRef('');
  const playbackLaunchInFlightRef = useRef('');
  const urlLessonHandoff = useMemo(() => (
    parseMotionPracticeLessonHandoff(searchParams)
  ), [searchParams]);
  const graphLessonHandoff = useMemo(() => {
    if (!urlLessonHandoff) {
      return null;
    }
    return buildMotionPracticeLessonHandoffFromGraphSelection({
      capabilityCode,
      graphSelection: aolHost?.graphSelection ?? null,
    });
  }, [aolHost, capabilityCode, urlLessonHandoff]);
  const lessonHandoff = agentLessonHandoff || graphLessonHandoff || urlLessonHandoff;
  const clientActionMeetingId = readString(searchParams.get('meeting'))
    || readString(searchParams.get('meeting_session_id'))
    || readString(aolHost?.activeMeetingId)
    || readString(aolHost?.meetingId);
  const initialInstructionSource = useMemo(() => (
    buildInstructionSourceStateFromLessonHandoff(lessonHandoff)
  ), [lessonHandoff]);

  useEffect(() => {
    const previousSessionCount = previousSessionCountRef.current;
    previousSessionCountRef.current = sessions.length;
    if (previousSessionCount === 0 && sessions.length > 0) {
      requestPackScopeToolClose({
        capabilityCode,
        toolId: 'motion_source',
      });
    }
  }, [capabilityCode, sessions.length]);

  useEffect(() => {
    if (!sessions.length) {
      setSelectedSessionId('');
      return;
    }
    if (!selectedSessionId || !sessions.some((session) => session.session_id === selectedSessionId)) {
      setSelectedSessionId(sessions[0].session_id);
    }
  }, [selectedSessionId, sessions]);

  const selectedSession = useMemo(() => (
    sessions.find((session) => session.session_id === selectedSessionId) || sessions[0] || null
  ), [selectedSessionId, sessions]);

  useEffect(() => {
    return subscribeMeetingClientActions((action) => {
      if (
        !action
        || action.workspaceId !== workspaceId
        || action.packCode !== resolveCoachPack(capabilityCode)
        || (clientActionMeetingId && action.meetingId !== clientActionMeetingId)
      ) {
        return;
      }
      const prepared = prepareMotionPracticeReferencePlayback(action);
      if (prepared) {
        setAgentLessonHandoff(prepared.handoff);
        setReferencePlaybackPlan(prepared.plan);
        setPracticeResult(null);
        setClosureResult(null);
        setMotionWindowEvents([]);
        return;
      }
      setReferencePlaybackPlan((current) => (
        confirmMotionPracticeReferencePlayback(current, action) || current
      ));
    }, clientActionMeetingId ? {
      apiUrl,
      workspaceId,
      meetingId: clientActionMeetingId,
    } : undefined);
  }, [apiUrl, capabilityCode, clientActionMeetingId, workspaceId]);

  useEffect(() => {
    if (!referencePlaybackPlan || referencePlaybackPlan.status !== 'countdown') {
      return undefined;
    }
    if (referencePlaybackPlan.countdownRemaining > 0) {
      const timer = window.setTimeout(() => {
        setReferencePlaybackPlan((current) => (
          current?.status === 'countdown'
            ? { ...current, countdownRemaining: Math.max(0, current.countdownRemaining - 1) }
            : current
        ));
      }, 1000);
      return () => window.clearTimeout(timer);
    }
    const confirmationActionId = referencePlaybackPlan.confirmationActionId || '';
    if (!confirmationActionId) {
      return undefined;
    }
    if (!selectedSession || !agentLessonHandoff) {
      setReferencePlaybackPlan((current) => current ? {
        ...current,
        status: 'failed',
        error: selectedSession ? 'reference_handoff_missing' : 'learner_source_not_connected',
      } : current);
      return undefined;
    }
    const launchKey = [
      workspaceId,
      referencePlaybackPlan.meetingId,
      selectedSession.session_id,
      selectedSession.media_session_id || '',
      resolveCoachPack(capabilityCode),
      confirmationActionId,
    ].join(':');
    if (playbackLaunchInFlightRef.current === launchKey) {
      return undefined;
    }
    playbackLaunchInFlightRef.current = launchKey;
    const input: MotionPracticeLaunchInput = {
      apiUrl,
      workspaceId,
      activeGroupId: workspaceGroup?.activeGroup?.id,
      observedTopologyRevision: workspaceGroup?.activeGroup?.revision,
      sourceSession: selectedSession,
      meetingSessionId: referencePlaybackPlan.meetingId,
      coachPack: resolveCoachPack(capabilityCode),
      practiceMode: 'live_guidance',
      expertLibraryRef: agentLessonHandoff.sourceValue,
      instructionRefs: buildInstructionRefsFromLessonHandoff(agentLessonHandoff),
      userGoal: 'Follow the selected reference lesson while motion-sequence localization aligns learner capture.',
      expectedDurationMs: referencePlaybackPlan.playback.durationMs,
    };
    if (hasAttachedMediaReceiver(selectedSession)) {
      const attachedResult = buildAttachedMotionPracticeResult(
        selectedSession,
        input.coachPack,
      );
      if (!attachedResult) {
        setReferencePlaybackPlan((current) => current ? {
          ...current,
          status: 'failed',
          error: 'media_analysis_handoff_missing',
        } : current);
        return undefined;
      }
      const elapsedMs = Math.min(
        Math.max(0, selectedSession.media_receiver_metrics?.last_window_end_ms || 0),
        Math.max(0, referencePlaybackPlan.playback.durationMs - 1),
      );
      setReferencePlaybackPlan((current) => current ? {
        ...current,
        status: 'playing',
        playback: {
          ...current.playback,
          startMs: current.playback.startMs + elapsedMs,
        },
        startedAt: new Date(Date.now() - elapsedMs).toISOString(),
        error: undefined,
      } : current);
      setLaunchInput(input);
      setPracticeResult(attachedResult);
      setClosureResult(null);
      setMotionWindowEvents([]);
      return undefined;
    }
    setLaunchInput(input);
    setReferencePlaybackPlan((current) => current ? { ...current, status: 'starting' } : current);
    void launchMotionPracticeOnce(launchKey, input).then((result) => {
      setPracticeResult(result);
      setClosureResult(null);
      setMotionWindowEvents([]);
      setReferencePlaybackPlan((current) => current ? {
        ...current,
        status: 'playing',
        startedAt: new Date().toISOString(),
        error: undefined,
      } : current);
    }).catch((error) => {
      setReferencePlaybackPlan((current) => current ? {
        ...current,
        status: 'failed',
        error: error instanceof Error ? error.message : 'motion_practice_launch_failed',
      } : current);
    });
    return undefined;
  }, [
    agentLessonHandoff,
    apiUrl,
    capabilityCode,
    referencePlaybackPlan,
    selectedSession,
    workspaceGroup?.activeGroup?.id,
    workspaceGroup?.activeGroup?.revision,
    workspaceId,
  ]);

  useEffect(() => {
    if (!referencePlaybackPlan?.startedAt || referencePlaybackPlan.status !== 'playing') {
      return undefined;
    }
    const elapsedMs = Date.now() - Date.parse(referencePlaybackPlan.startedAt);
    const remainingMs = Math.max(0, referencePlaybackPlan.playback.durationMs - elapsedMs);
    const timer = window.setTimeout(() => {
      setReferencePlaybackPlan((current) => (
        current?.status === 'playing' ? { ...current, status: 'complete' } : current
      ));
    }, remainingMs);
    return () => window.clearTimeout(timer);
  }, [referencePlaybackPlan]);

  const scopedPracticeResult = useMemo(() => (
    practiceResult?.coachPack === resolveCoachPack(capabilityCode) ? practiceResult : null
  ), [capabilityCode, practiceResult]);

  const scopedMotionWindowEvents = useMemo(() => {
    if (!scopedPracticeResult?.liveSessionId) {
      return [];
    }
    return motionWindowEvents.filter((event) => (
      event.liveSessionId === scopedPracticeResult.liveSessionId
    ));
  }, [motionWindowEvents, scopedPracticeResult?.liveSessionId]);

  const workbenchState = useMemo(() => {
    const input = {
      capabilityCode,
      selectedSession,
      referenceLessonState,
      pendingLessonHandoff: lessonHandoff,
      launchInput,
      practiceResult: scopedPracticeResult,
      motionWindowEvents: scopedMotionWindowEvents,
      closureResult,
    };
    return capabilityCode === 'dance_motion_coach'
      ? buildDancePracticeWorkbenchState(input)
      : buildYogaPracticeWorkbenchState(input);
  }, [
    capabilityCode,
    closureResult,
    lessonHandoff,
    launchInput,
    referenceLessonState,
    scopedMotionWindowEvents,
    scopedPracticeResult,
    selectedSession,
  ]);

  const referenceLessonDeviceState = useMemo(
    () => buildReferenceLessonDeviceState(workbenchState),
    [workbenchState],
  );

  useEffect(() => {
    const nextKey = JSON.stringify(referenceLessonDeviceState || null);
    if (publishedReferenceLessonKeyRef.current === nextKey) {
      return;
    }
    publishedReferenceLessonKeyRef.current = nextKey;
    captureSourceBridge.publishReferenceLessonState(referenceLessonDeviceState);
  }, [captureSourceBridge, referenceLessonDeviceState]);

  const liveMotionSessionId = scopedPracticeResult
    && scopedPracticeResult.sourceSessionId === selectedSession?.session_id
    ? scopedPracticeResult.liveSessionId
    : null;

  const recoverLiveMotionSession = useCallback(async (lostLiveSessionId: string) => {
    if (
      !lostLiveSessionId ||
      !launchInput ||
      !scopedPracticeResult ||
      scopedPracticeResult.liveSessionId !== lostLiveSessionId ||
      recoveryInFlightRef.current === lostLiveSessionId
    ) {
      return;
    }
    recoveryInFlightRef.current = lostLiveSessionId;
    setPracticeResult(null);
    setClosureResult(null);
    setMotionWindowEvents((current) => (
      current.filter((event) => event.liveSessionId !== lostLiveSessionId)
    ));
    try {
      const nextResult = await launchMotionPractice({
        ...launchInput,
        sourceSession: selectedSession || launchInput.sourceSession,
      });
      setPracticeResult(nextResult);
      if (nextResult.sourceSessionId) {
        setSelectedSessionId(nextResult.sourceSessionId);
      }
    } finally {
      if (recoveryInFlightRef.current === lostLiveSessionId) {
        recoveryInFlightRef.current = '';
      }
    }
  }, [launchInput, scopedPracticeResult, selectedSession]);

  const hostCapturePreview = selectedSession ? (
    <PhoneSourcePreview
      apiUrl={apiUrl}
      workspaceId={workspaceId}
      session={selectedSession}
      liveMotionSessionId={liveMotionSessionId}
      onMotionWindowAppended={(event) => {
        setMotionWindowEvents((current) => (
          [...current, event].slice(-MAX_WINDOW_EVENTS)
        ));
      }}
      onLiveMotionSessionLost={(lostLiveSessionId) => {
        void recoverLiveMotionSession(lostLiveSessionId);
      }}
      className="mt-0 h-full min-h-0 w-full border-stone-900 shadow-sm"
    />
  ) : (
    <div
      className="flex h-full min-h-[320px] w-full items-center justify-center rounded-lg border border-dashed border-stone-300 bg-stone-100 px-6 text-center text-sm text-stone-500"
      data-testid="motion-coach-host-capture-placeholder"
    >
      Connect a phone, OBS, or desktop camera from Motion source to open the learner stage.
    </div>
  );

  return (
    <div className="relative flex h-full min-h-0 min-w-0 flex-1 overflow-hidden bg-stone-100" data-testid="motion-coach-workbench-host">
      <Component
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        aolHost={aolHost}
        surfacePath={surfacePath}
        taskConfirmation={taskConfirmation}
        workbenchState={workbenchState}
        referencePlaybackPlan={referencePlaybackPlan}
        hostCapturePreview={hostCapturePreview}
        motionCoachControls={{
          workspaceId,
          apiUrl,
          capabilityCode,
          coachPackLock: resolveCoachPack(capabilityCode),
          sessions,
          selectedSessionId,
          captureSourceBridge,
          initialInstructionSource,
          result: scopedPracticeResult,
          latestWindowAppend: scopedMotionWindowEvents[scopedMotionWindowEvents.length - 1] || null,
          onSelectedSessionChange: setSelectedSessionId,
          onResultChange: (nextResult: MotionPracticeLaunchResult | null) => {
            setPracticeResult(nextResult);
            setClosureResult(null);
            setMotionWindowEvents([]);
            if (nextResult?.sourceSessionId) {
              setSelectedSessionId(nextResult.sourceSessionId);
            }
          },
          onLaunchInputChange: setLaunchInput,
          onClosureResultChange: setClosureResult,
        }}
      />
    </div>
  );
}

export default function MotionCoachWorkbenchHost(props: MotionCoachWorkbenchHostProps) {
  const existingBridge = useOptionalCaptureSourceBridge();

  if (existingBridge) {
    return <MotionCoachWorkbenchHostContent {...props} />;
  }

  return (
    <CaptureSourceBridgeProvider
      apiUrl={props.apiUrl}
      workspaceId={props.workspaceId}
    >
      <MotionCoachWorkbenchHostContent {...props} />
    </CaptureSourceBridgeProvider>
  );
}

'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import {
  CaptureSourceBridgeProvider,
  type CaptureSourceReferenceLessonState,
  useCaptureSourceBridge,
  useOptionalCaptureSourceBridge,
} from '@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider';
import { PhoneSourcePreview } from '@/components/workspace/device-binding/PhoneSourcePreview';
import type { MotionPracticeClosureResult } from '@/components/workspace/device-binding/motionPracticeClosure';
import type { MotionPracticeLaunchInput, MotionPracticeLaunchResult, MotionPracticeCoachPack } from '@/components/workspace/device-binding/motionPracticeLauncher';
import type { MotionWindowAppendEvent } from '@/components/workspace/device-binding/motionWindowAppendEvent';
import {
  buildInstructionSourceStateFromLessonHandoff,
  parseMotionPracticeLessonHandoff,
} from '@/components/workspace/device-binding/practice/motionPracticeLessonHandoff';
import { buildMotionPracticeLessonHandoffFromGraphSelection } from '@/components/workspace/device-binding/practice/motionPracticeGraphSelection';
import type { CapabilityTaskConfirmationBridge } from '@/types/capability-workbench';
import { requestPackScopeToolClose } from '@/components/capabilities/workbench/packScopeToolEvents';
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

function resolveCoachPack(capabilityCode: MotionCoachCapabilityCode): MotionPracticeCoachPack {
  return capabilityCode === 'dance_motion_coach' ? 'dance_motion_coach' : 'yogacoach';
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
  const searchParams = useSearchParams();
  const captureSourceBridge = useCaptureSourceBridge();
  const { sessions, referenceLessonState } = captureSourceBridge;
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [practiceResult, setPracticeResult] = useState<MotionPracticeLaunchResult | null>(null);
  const [launchInput, setLaunchInput] = useState<MotionPracticeLaunchInput | null>(null);
  const [motionWindowEvents, setMotionWindowEvents] = useState<MotionWindowAppendEvent[]>([]);
  const [closureResult, setClosureResult] = useState<MotionPracticeClosureResult | null>(null);
  const publishedReferenceLessonKeyRef = useRef('');
  const previousSessionCountRef = useRef(sessions.length);
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
  const lessonHandoff = graphLessonHandoff || urlLessonHandoff;
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

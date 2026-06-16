'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import {
  CaptureSourceBridgeProvider,
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
}

const MAX_WINDOW_EVENTS = 60;

function resolveCoachPack(capabilityCode: MotionCoachCapabilityCode): MotionPracticeCoachPack {
  return capabilityCode === 'dance_motion_coach' ? 'dance_motion_coach' : 'yogacoach';
}

function MotionCoachWorkbenchHostContent({
  workspaceId,
  apiUrl,
  capabilityCode,
  Component,
  aolHost,
  surfacePath,
}: MotionCoachWorkbenchHostProps) {
  const searchParams = useSearchParams();
  const { sessions, referenceLessonState } = useCaptureSourceBridge();
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [practiceResult, setPracticeResult] = useState<MotionPracticeLaunchResult | null>(null);
  const [launchInput, setLaunchInput] = useState<MotionPracticeLaunchInput | null>(null);
  const [motionWindowEvents, setMotionWindowEvents] = useState<MotionWindowAppendEvent[]>([]);
  const [closureResult, setClosureResult] = useState<MotionPracticeClosureResult | null>(null);
  const lessonHandoff = useMemo(() => (
    parseMotionPracticeLessonHandoff(searchParams)
  ), [searchParams]);
  const initialInstructionSource = useMemo(() => (
    buildInstructionSourceStateFromLessonHandoff(lessonHandoff)
  ), [lessonHandoff]);

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
      className="mt-0 border-stone-900 shadow-sm"
    />
  ) : (
    <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-stone-300 bg-stone-100 px-6 text-center text-sm text-stone-500">
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
        workbenchState={workbenchState}
        hostCapturePreview={hostCapturePreview}
        motionCoachControls={{
          workspaceId,
          apiUrl,
          capabilityCode,
          coachPackLock: resolveCoachPack(capabilityCode),
          sessions,
          selectedSessionId,
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

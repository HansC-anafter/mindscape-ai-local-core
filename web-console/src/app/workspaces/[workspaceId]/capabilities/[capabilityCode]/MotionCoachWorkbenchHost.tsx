'use client';

import React, { useEffect, useMemo, useState } from 'react';

import { CaptureSourceBridgeProvider, useCaptureSourceBridge } from '@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider';
import { CaptureSourceRail } from '@/components/workspace/device-binding/capture-bridge/CaptureSourceRail';
import { PhoneSourcePreview } from '@/components/workspace/device-binding/PhoneSourcePreview';
import type { MotionPracticeClosureResult } from '@/components/workspace/device-binding/motionPracticeClosure';
import type { MotionPracticeLaunchInput, MotionPracticeLaunchResult, MotionPracticeCoachPack } from '@/components/workspace/device-binding/motionPracticeLauncher';
import type { MotionWindowAppendEvent } from '@/components/workspace/device-binding/motionWindowAppendEvent';
import { MotionPracticeRailController } from '@/components/workspace/device-binding/practice/MotionPracticeRailController';
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
  const { sessions, referenceLessonState } = useCaptureSourceBridge();
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [practiceResult, setPracticeResult] = useState<MotionPracticeLaunchResult | null>(null);
  const [launchInput, setLaunchInput] = useState<MotionPracticeLaunchInput | null>(null);
  const [motionWindowEvents, setMotionWindowEvents] = useState<MotionWindowAppendEvent[]>([]);
  const [closureResult, setClosureResult] = useState<MotionPracticeClosureResult | null>(null);

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
    launchInput,
    referenceLessonState,
    scopedMotionWindowEvents,
    scopedPracticeResult,
    selectedSession,
  ]);

  const liveMotionSessionId = scopedPracticeResult?.sourceSessionId === selectedSession?.session_id
    ? scopedPracticeResult.liveSessionId
    : null;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-stone-50 xl:flex-row" data-testid="motion-coach-workbench-host">
      <aside className="w-full shrink-0 overflow-y-auto border-b border-stone-200 bg-white xl:h-full xl:w-[360px] xl:border-b-0 xl:border-r">
        <div className="space-y-4 p-4">
          <section className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase text-stone-500">Motion Source</p>
              <h2 className="mt-1 text-sm font-semibold text-stone-900">Device binding and source readiness</h2>
            </div>
            <CaptureSourceRail
              apiUrl={apiUrl}
              workspaceId={workspaceId}
              showPreview={false}
            />
          </section>

          <section className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase text-stone-500">Practice Control</p>
              <h2 className="mt-1 text-sm font-semibold text-stone-900">Launch analysis and guidance</h2>
            </div>
            <MotionPracticeRailController
              apiUrl={apiUrl}
              workspaceId={workspaceId}
              sessions={sessions}
              result={scopedPracticeResult}
              latestWindowAppend={scopedMotionWindowEvents[scopedMotionWindowEvents.length - 1] || null}
              selectedSessionId={selectedSessionId}
              onSelectedSessionChange={setSelectedSessionId}
              onResultChange={(nextResult) => {
                setPracticeResult(nextResult);
                setClosureResult(null);
                setMotionWindowEvents([]);
                if (nextResult?.sourceSessionId) {
                  setSelectedSessionId(nextResult.sourceSessionId);
                }
              }}
              onLaunchInputChange={setLaunchInput}
              onClosureResultChange={setClosureResult}
              coachPackLock={resolveCoachPack(capabilityCode)}
              defaultPracticeMode="live_guidance"
            />
          </section>

          <section className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase text-stone-500">Receiver</p>
              <h2 className="mt-1 text-sm font-semibold text-stone-900">Selected learner stream</h2>
            </div>
            {selectedSession ? (
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
              />
            ) : (
              <div className="rounded-md border border-dashed border-stone-200 bg-stone-50 px-3 py-3 text-sm text-stone-500">
                Connect a phone, OBS, or desktop camera to start the workspace receiver.
              </div>
            )}
          </section>
        </div>
      </aside>

      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <Component
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          aolHost={aolHost}
          surfacePath={surfacePath}
          workbenchState={workbenchState}
        />
      </div>
    </div>
  );
}

export default function MotionCoachWorkbenchHost(props: MotionCoachWorkbenchHostProps) {
  return (
    <CaptureSourceBridgeProvider
      apiUrl={props.apiUrl}
      workspaceId={props.workspaceId}
    >
      <MotionCoachWorkbenchHostContent {...props} />
    </CaptureSourceBridgeProvider>
  );
}

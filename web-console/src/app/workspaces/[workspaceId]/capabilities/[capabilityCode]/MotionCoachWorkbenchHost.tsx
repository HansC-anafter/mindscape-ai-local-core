'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Camera, Radio, X } from 'lucide-react';

import {
  CaptureSourceBridgeProvider,
  useCaptureSourceBridge,
  useOptionalCaptureSourceBridge,
} from '@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider';
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

type MotionCoachHostPanel = 'source' | 'practice' | null;

function cn(...classes: Array<string | null | undefined | false>): string {
  return classes.filter(Boolean).join(' ');
}

function resolveCoachPack(capabilityCode: MotionCoachCapabilityCode): MotionPracticeCoachPack {
  return capabilityCode === 'dance_motion_coach' ? 'dance_motion_coach' : 'yogacoach';
}

function HostToolButton({
  active,
  icon,
  label,
  detail,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex min-w-[132px] items-center gap-3 rounded-lg border px-3 py-2 text-left shadow-sm transition',
        active
          ? 'border-emerald-300 bg-emerald-50 text-emerald-950'
          : 'border-stone-200 bg-white/95 text-stone-700 hover:border-stone-300 hover:bg-white',
      )}
    >
      <span
        className={cn(
          'inline-flex h-9 w-9 items-center justify-center rounded-md border',
          active
            ? 'border-emerald-300 bg-white text-emerald-700'
            : 'border-stone-200 bg-stone-50 text-stone-500',
        )}
      >
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold">{label}</span>
        <span className="block truncate text-xs text-stone-500">{detail}</span>
      </span>
    </button>
  );
}

function HostToolDrawer({
  open,
  title,
  description,
  onClose,
  children,
  testId,
}: {
  open: boolean;
  title: string;
  description: string;
  onClose: () => void;
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <aside
      className={cn(
        'absolute inset-x-0 bottom-0 z-40 flex max-h-[78vh] w-full transform flex-col overflow-hidden rounded-t-[20px] border-t border-stone-200 bg-white shadow-2xl transition duration-200 md:inset-y-0 md:right-0 md:left-auto md:max-h-full md:max-w-[420px] md:rounded-none md:border-l md:border-t-0',
        open
          ? 'translate-y-0 md:translate-x-0'
          : 'translate-y-full md:translate-x-full',
      )}
      data-testid={testId}
      aria-hidden={!open}
    >
      <div className="flex items-start justify-between gap-4 border-b border-stone-200 px-4 py-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-stone-500">Motion coach tools</p>
          <h2 className="mt-1 text-base font-semibold text-stone-950">{title}</h2>
          <p className="mt-1 text-sm text-stone-600">{description}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-stone-200 bg-white text-stone-500 transition hover:bg-stone-50 hover:text-stone-900"
          aria-label={`Close ${title}`}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </aside>
  );
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
  const [activePanel, setActivePanel] = useState<MotionCoachHostPanel>(null);

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

  const liveMotionSessionId = scopedPracticeResult
    && scopedPracticeResult.sourceSessionId === selectedSession?.session_id
    ? scopedPracticeResult.liveSessionId
    : null;
  const hostStatus = workbenchState as {
    connected_capture_source_ref?: { status?: string };
    live_motion_session_ref?: { status?: string };
  };

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

  const sourceStatusLabel = selectedSession?.display_name || 'No source connected';
  const practiceStatusLabel = scopedPracticeResult?.liveGuidanceEnabled
    ? 'Live guidance ready'
    : 'Practice launch pending';

  return (
    <div className="relative flex h-full min-h-0 min-w-0 flex-1 overflow-hidden bg-stone-100" data-testid="motion-coach-workbench-host">
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden pb-24 lg:pb-0">
        <Component
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          aolHost={aolHost}
          surfacePath={surfacePath}
          workbenchState={workbenchState}
          hostCapturePreview={hostCapturePreview}
          onOpenDeviceBindingPanel={() => setActivePanel('source')}
          onOpenPracticeSetupPanel={() => setActivePanel('practice')}
        />
      </div>

      <div className="pointer-events-none absolute right-4 top-4 z-30 hidden lg:block">
        <div className="pointer-events-auto flex flex-col items-end gap-2">
          <div className="rounded-full border border-stone-200 bg-white/95 px-3 py-1.5 text-xs font-semibold text-stone-600 shadow-sm">
            {hostStatus.connected_capture_source_ref?.status || 'pairing'} · {hostStatus.live_motion_session_ref?.status || 'idle'}
          </div>
          <HostToolButton
            active={activePanel === 'source'}
            icon={<Camera className="h-4 w-4" aria-hidden="true" />}
            label="Motion source"
            detail={sourceStatusLabel}
            onClick={() => setActivePanel((current) => (current === 'source' ? null : 'source'))}
          />
          <HostToolButton
            active={activePanel === 'practice'}
            icon={<Radio className="h-4 w-4" aria-hidden="true" />}
            label="Practice setup"
            detail={practiceStatusLabel}
            onClick={() => setActivePanel((current) => (current === 'practice' ? null : 'practice'))}
          />
        </div>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-4 z-30 px-4 lg:hidden">
        <div className="pointer-events-auto mx-auto flex w-full max-w-sm items-center gap-2 rounded-2xl border border-stone-200 bg-white/95 p-2 shadow-xl backdrop-blur">
          <button
            type="button"
            onClick={() => setActivePanel((current) => (current === 'source' ? null : 'source'))}
            className={cn(
              'flex min-h-12 flex-1 items-center gap-3 rounded-xl border px-3 py-2 text-left transition',
              activePanel === 'source'
                ? 'border-emerald-300 bg-emerald-50 text-emerald-950'
                : 'border-stone-200 bg-white text-stone-700',
            )}
          >
            <span
              className={cn(
                'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border',
                activePanel === 'source'
                  ? 'border-emerald-300 bg-white text-emerald-700'
                  : 'border-stone-200 bg-stone-50 text-stone-500',
              )}
            >
              <Camera className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">Source</span>
              <span className="block truncate text-xs text-stone-500">{sourceStatusLabel}</span>
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActivePanel((current) => (current === 'practice' ? null : 'practice'))}
            className={cn(
              'flex min-h-12 flex-1 items-center gap-3 rounded-xl border px-3 py-2 text-left transition',
              activePanel === 'practice'
                ? 'border-sky-300 bg-sky-50 text-sky-950'
                : 'border-stone-200 bg-white text-stone-700',
            )}
          >
            <span
              className={cn(
                'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border',
                activePanel === 'practice'
                  ? 'border-sky-300 bg-white text-sky-700'
                  : 'border-stone-200 bg-stone-50 text-stone-500',
              )}
            >
              <Radio className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">Practice</span>
              <span className="block truncate text-xs text-stone-500">{practiceStatusLabel}</span>
            </span>
          </button>
        </div>
      </div>

      <div
        className={cn(
          'absolute inset-0 z-20 bg-stone-950/20 transition duration-200',
          activePanel ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={() => setActivePanel(null)}
      />

      <HostToolDrawer
        open={activePanel === 'source'}
        title="Device binding and source readiness"
        description="Pair phone, iPad, desktop camera, or OBS here. The domain workbench stays focused on the lesson."
        onClose={() => setActivePanel(null)}
        testId="motion-coach-source-drawer"
      >
        <CaptureSourceRail
          apiUrl={apiUrl}
          workspaceId={workspaceId}
          showPreview={false}
        />
      </HostToolDrawer>

      <HostToolDrawer
        open={activePanel === 'practice'}
        title="Practice launch and guidance controls"
        description="Choose source, lesson reference, and workflow here. Launch remains generic at the host layer."
        onClose={() => setActivePanel(null)}
        testId="motion-coach-practice-drawer"
      >
        <div className="p-4">
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
        </div>
      </HostToolDrawer>
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

'use client';

import React, { useMemo, useState } from 'react';
import { BookOpenCheck, Loader2, PlayCircle } from 'lucide-react';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import {
  buildMotionPracticeIntentText,
  launchMotionPractice,
  resolveMotionPracticeTarget,
  type MotionPracticeCoachPack,
  type MotionPracticeLaunchResult,
  type MotionPracticeMode,
} from '../motionPracticeLauncher';
import {
  buildMotionPracticeInstructionRefs,
  DEFAULT_MOTION_PRACTICE_INSTRUCTION_SOURCE,
  MotionPracticeInstructionSourcePanel,
  type MotionPracticeInstructionSourceState,
} from './MotionPracticeInstructionSourcePanel';
import { MotionPracticeRecordsPanel } from './MotionPracticeRecordsPanel';
import {
  MotionPracticeSessionStatusPanel,
  type MotionPracticeLaunchState,
} from './MotionPracticeSessionStatusPanel';

interface MotionPracticeRailControllerProps {
  apiUrl: string;
  workspaceId: string;
  sessions: DeviceSessionEntry[];
  result: MotionPracticeLaunchResult | null;
  onResultChange: (result: MotionPracticeLaunchResult | null) => void;
}

export function MotionPracticeRailController({
  apiUrl,
  workspaceId,
  sessions,
  result,
  onResultChange,
}: MotionPracticeRailControllerProps) {
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [coachPack, setCoachPack] = useState<MotionPracticeCoachPack>('yogacoach');
  const [practiceMode, setPracticeMode] = useState<MotionPracticeMode>('record_summary');
  const [expertLibraryRef, setExpertLibraryRef] = useState('');
  const [userGoal, setUserGoal] = useState('');
  const [instructionSource, setInstructionSource] =
    useState<MotionPracticeInstructionSourceState>(
      DEFAULT_MOTION_PRACTICE_INSTRUCTION_SOURCE,
    );
  const [launchState, setLaunchState] = useState<MotionPracticeLaunchState>('idle');
  const [launchError, setLaunchError] = useState<string | null>(null);

  const target = useMemo(
    () => resolveMotionPracticeTarget(coachPack, practiceMode),
    [coachPack, practiceMode],
  );
  const selectedSession = useMemo(() => (
    sessions.find((session) => session.session_id === selectedSessionId) || sessions[0] || null
  ), [selectedSessionId, sessions]);
  const instructionRefs = useMemo(
    () => buildMotionPracticeInstructionRefs(instructionSource),
    [instructionSource],
  );
  const commandPreview = useMemo(() => (
    selectedSession
      ? buildMotionPracticeIntentText({
          apiUrl,
          workspaceId,
          sourceSession: selectedSession,
          coachPack,
          practiceMode,
          expertLibraryRef,
          instructionRefs,
          userGoal,
        })
      : ''
  ), [
    apiUrl,
    coachPack,
    expertLibraryRef,
    instructionRefs,
    practiceMode,
    selectedSession,
    userGoal,
    workspaceId,
  ]);

  const startPractice = async () => {
    if (!selectedSession || !target.enabled || !target.playbookCode) {
      return;
    }
    setLaunchState('starting');
    setLaunchError(null);
    onResultChange(null);
    try {
      const nextResult = await launchMotionPractice({
        apiUrl,
        workspaceId,
        sourceSession: selectedSession,
        coachPack,
        practiceMode,
        expertLibraryRef,
        instructionRefs,
        userGoal,
      });
      onResultChange(nextResult);
      setLaunchState('submitted');
    } catch (nextError) {
      setLaunchError(nextError instanceof Error ? nextError.message : 'motion_practice_launch_failed');
      setLaunchState('error');
    }
  };

  const copyPracticeCommand = async () => {
    if (!commandPreview || typeof navigator === 'undefined' || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(commandPreview);
  };

  return (
    <div className="space-y-3 rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950">
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
        <BookOpenCheck className="h-4 w-4 text-emerald-600" aria-hidden="true" />
        Practice
      </div>

      {sessions.length ? (
        <label className="block">
          <span className="mb-1 block text-[11px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
            Motion source
          </span>
          <select
            value={selectedSession?.session_id || ''}
            onChange={(event) => setSelectedSessionId(event.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            data-testid="motion-practice-source-select"
          >
            {sessions.map((session) => (
              <option key={session.session_id} value={session.session_id}>
                {session.display_name || session.device_id} - {session.source_types.join(', ') || session.state}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Connect a phone, OBS virtual camera, or desktop camera before launching practice.
        </div>
      )}

      <div>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Coach
        </div>
        <div className="grid grid-cols-2 gap-1">
          <button
            type="button"
            onClick={() => setCoachPack('yogacoach')}
            className={`rounded-md border px-2 py-1.5 text-xs font-medium ${
              coachPack === 'yogacoach'
                ? 'border-emerald-500 bg-emerald-50 text-emerald-800 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-100'
                : 'border-gray-200 text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900'
            }`}
          >
            AI Yoga
          </button>
          <button
            type="button"
            onClick={() => setCoachPack('dance_motion_coach')}
            className={`rounded-md border px-2 py-1.5 text-xs font-medium ${
              coachPack === 'dance_motion_coach'
                ? 'border-emerald-500 bg-emerald-50 text-emerald-800 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-100'
                : 'border-gray-200 text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900'
            }`}
          >
            Dance
          </button>
        </div>
      </div>

      <label className="block">
        <span className="mb-1 block text-[11px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Workflow
        </span>
        <select
          value={practiceMode}
          onChange={(event) => setPracticeMode(event.target.value as MotionPracticeMode)}
          className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          data-testid="motion-practice-mode-select"
        >
          <option value="record_summary">Record + summary</option>
          <option value="teacher_assessment">Teacher assessment</option>
          <option value="live_guidance">Live guidance</option>
        </select>
      </label>

      <label className="block">
        <span className="mb-1 block text-[11px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Teacher/video ref
        </span>
        <input
          value={expertLibraryRef}
          onChange={(event) => setExpertLibraryRef(event.target.value)}
          placeholder="mindscape://yogacoach/teacher-library/..."
          className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        />
      </label>

      <MotionPracticeInstructionSourcePanel
        source={instructionSource}
        onChange={setInstructionSource}
      />

      <label className="block">
        <span className="mb-1 block text-[11px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Goal
        </span>
        <input
          value={userGoal}
          onChange={(event) => setUserGoal(event.target.value)}
          placeholder="alignment, rhythm, balance..."
          className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        />
      </label>

      <MotionPracticeSessionStatusPanel
        target={target}
        launchState={launchState}
        error={launchError}
        result={result}
      />

      <button
        type="button"
        onClick={() => void startPractice()}
        disabled={!selectedSession || !target.enabled || launchState === 'starting'}
        className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-500 dark:disabled:bg-gray-800 dark:disabled:text-gray-500"
        data-testid="motion-practice-start-button"
      >
        {launchState === 'starting'
          ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          : <PlayCircle className="h-4 w-4" aria-hidden="true" />}
        Start practice
      </button>

      <MotionPracticeRecordsPanel
        workspaceId={workspaceId}
        commandPreview={commandPreview}
        result={result}
        onCopyCommand={() => void copyPracticeCommand()}
      />
    </div>
  );
}

export default MotionPracticeRailController;

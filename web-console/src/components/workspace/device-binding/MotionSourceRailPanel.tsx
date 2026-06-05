'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookOpenCheck, Link2, Loader2, MonitorUp, PlayCircle, Smartphone, Unplug } from 'lucide-react';

import {
  createDevicePairingCode,
  openDeviceControlSocket,
  revokeDeviceSession,
  type DeviceControlEvent,
  type DeviceControlSocket,
  type DevicePairingCode,
  type DeviceSessionEntry,
} from '@/lib/device-binding/deviceBindingClient';
import { PhoneSourcePreview } from './PhoneSourcePreview';
import {
  buildMotionPracticeIntentText,
  launchMotionPractice,
  resolveMotionPracticeTarget,
  type MotionPracticeCoachPack,
  type MotionPracticeLaunchResult,
  type MotionPracticeMode,
} from './motionPracticeLauncher';

interface MotionSourceRailPanelProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
}

type PanelState = 'idle' | 'creating' | 'pairing' | 'connected' | 'error';
type PracticeLaunchState = 'idle' | 'starting' | 'submitted' | 'error';

function sortSessions(sessions: DeviceSessionEntry[]): DeviceSessionEntry[] {
  return [...sessions].sort((left, right) => left.created_at_epoch - right.created_at_epoch);
}

type DeviceLinkSourceMode = 'phone' | 'camera';

function buildDeviceLink(
  pairing: DevicePairingCode | null,
  workspaceId: string,
  sourceMode: DeviceLinkSourceMode,
): string {
  if (!pairing) {
    return '';
  }
  if (typeof window === 'undefined') {
    return `${pairing.device_link_path}?workspaceId=${encodeURIComponent(workspaceId)}&sourceMode=${sourceMode}`;
  }
  const url = new URL(pairing.device_link_path, window.location.origin);
  url.searchParams.set('workspaceId', workspaceId);
  url.searchParams.set('sourceMode', sourceMode);
  return url.toString();
}

export function MotionSourceRailPanel({
  apiUrl,
  workspaceId,
  disabled = false,
}: MotionSourceRailPanelProps) {
  const [state, setState] = useState<PanelState>('idle');
  const [pairing, setPairing] = useState<DevicePairingCode | null>(null);
  const [sessions, setSessions] = useState<DeviceSessionEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [coachPack, setCoachPack] = useState<MotionPracticeCoachPack>('yogacoach');
  const [practiceMode, setPracticeMode] = useState<MotionPracticeMode>('record_summary');
  const [expertLibraryRef, setExpertLibraryRef] = useState('');
  const [userGoal, setUserGoal] = useState('');
  const [practiceState, setPracticeState] = useState<PracticeLaunchState>('idle');
  const [practiceError, setPracticeError] = useState<string | null>(null);
  const [practiceResult, setPracticeResult] = useState<MotionPracticeLaunchResult | null>(null);
  const socketRef = useRef<DeviceControlSocket | null>(null);

  useEffect(() => () => socketRef.current?.close(), []);

  const phoneDeviceLink = useMemo(() => (
    buildDeviceLink(pairing, workspaceId, 'phone')
  ), [pairing, workspaceId]);
  const desktopDeviceLink = useMemo(() => (
    buildDeviceLink(pairing, workspaceId, 'camera')
  ), [pairing, workspaceId]);
  const target = useMemo(
    () => resolveMotionPracticeTarget(coachPack, practiceMode),
    [coachPack, practiceMode],
  );
  const selectedSession = useMemo(() => (
    sessions.find((session) => session.session_id === selectedSessionId) || sessions[0] || null
  ), [selectedSessionId, sessions]);
  const practiceCommandPreview = useMemo(() => (
    selectedSession
      ? buildMotionPracticeIntentText({
          apiUrl,
          workspaceId,
          sourceSession: selectedSession,
          coachPack,
          practiceMode,
          expertLibraryRef,
          userGoal,
        })
      : ''
  ), [apiUrl, coachPack, expertLibraryRef, practiceMode, selectedSession, userGoal, workspaceId]);

  const applyEvent = useCallback((event: DeviceControlEvent) => {
    if (event.type === 'pairing_ready') {
      setState('pairing');
    }
    if (event.type === 'session_paired' || event.type === 'session_active') {
      setState('connected');
    }
    if (event.type === 'session_revoked' || event.type === 'session_closed' || event.type === 'session_expired') {
      setState(event.active_sessions?.length ? 'connected' : 'pairing');
    }
    if (event.type === 'session_error' || event.type === 'session_rejected') {
      setState('error');
      setError(event.reason || event.message || 'device_binding_error');
    }
    if (event.active_sessions) {
      setSessions(sortSessions(event.active_sessions));
    }
  }, []);

  useEffect(() => {
    if (!sessions.length) {
      setSelectedSessionId('');
      return;
    }
    if (!sessions.some((session) => session.session_id === selectedSessionId)) {
      setSelectedSessionId(sessions[0].session_id);
    }
  }, [selectedSessionId, sessions]);

  const startPairing = useCallback(async () => {
    if (disabled || state === 'creating') {
      return;
    }
    setState('creating');
    setError(null);
    setSessions([]);
    socketRef.current?.close();
    try {
      const nextPairing = await createDevicePairingCode({
        apiBase: apiUrl,
        workspaceId,
      });
      setPairing(nextPairing);
      const socket = openDeviceControlSocket({
        apiBase: apiUrl,
        workspaceId,
        pairingCode: nextPairing.pairing_code,
        onOpen: () => socket.send({ type: 'workspace_subscribe' }),
        onEvent: applyEvent,
        onError: (nextError) => {
          setError(nextError.message);
          setState('error');
        },
      });
      socketRef.current = socket;
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'device_pairing_failed');
      setState('error');
    }
  }, [apiUrl, applyEvent, disabled, state, workspaceId]);

  useEffect(() => {
    if (state === 'idle' && !pairing && !disabled) {
      void startPairing();
    }
  }, [disabled, pairing, startPairing, state]);

  const revokeSession = async (sessionId: string) => {
    try {
      await revokeDeviceSession({
        apiBase: apiUrl,
        workspaceId,
        sessionId,
      });
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'device_revoke_failed');
      setState('error');
    }
  };

  const startPractice = async () => {
    if (!selectedSession || !target.enabled || !target.playbookCode) {
      return;
    }
    setPracticeState('starting');
    setPracticeError(null);
    setPracticeResult(null);
    try {
      const result = await launchMotionPractice({
        apiUrl,
        workspaceId,
        sourceSession: selectedSession,
        coachPack,
        practiceMode,
        expertLibraryRef,
        userGoal,
      });
      setPracticeResult(result);
      setPracticeState('submitted');
    } catch (nextError) {
      setPracticeError(nextError instanceof Error ? nextError.message : 'motion_practice_launch_failed');
      setPracticeState('error');
    }
  };

  const copyPracticeCommand = async () => {
    if (!practiceCommandPreview || typeof navigator === 'undefined' || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(practiceCommandPreview);
  };

  return (
    <div className="flex min-h-full flex-col gap-3 p-3 text-xs">
      <div className="rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900">
        <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          <Smartphone className="h-4 w-4 text-sky-500" aria-hidden="true" />
          Motion source
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400" data-testid="motion-source-rail-state">
          {state}
        </div>
      </div>

      {pairing ? (
        <div className="space-y-2 rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950">
          <div className="mb-2 flex items-center gap-1 font-mono text-sm font-semibold text-gray-900 dark:text-gray-100">
            <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
            {pairing.pairing_code}
          </div>
          <div className="rounded border border-gray-200 p-2 dark:border-gray-800">
            <div className="mb-1 flex items-center gap-1 font-medium text-gray-800 dark:text-gray-100">
              <Smartphone className="h-3.5 w-3.5 text-sky-500" aria-hidden="true" />
              Phone
            </div>
            <a
              href={phoneDeviceLink}
              target="_blank"
              rel="noreferrer"
              aria-label="Phone source link"
              className="block break-all text-xs text-sky-700 hover:text-sky-800 dark:text-sky-300"
            >
              {phoneDeviceLink}
            </a>
          </div>
          <div className="rounded border border-gray-200 p-2 dark:border-gray-800">
            <div className="mb-1 flex items-center gap-1 font-medium text-gray-800 dark:text-gray-100">
              <MonitorUp className="h-3.5 w-3.5 text-sky-500" aria-hidden="true" />
              This computer / OBS
            </div>
            <a
              href={desktopDeviceLink}
              target="_blank"
              rel="noreferrer"
              aria-label="Desktop camera source link"
              className="block break-all text-xs text-sky-700 hover:text-sky-800 dark:text-sky-300"
            >
              {desktopDeviceLink}
            </a>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-2 py-1.5 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
          {error}
        </div>
      ) : null}

      <div className="space-y-2">
        {sessions.map((session) => (
          <div
            key={session.session_id}
            className="rounded-md border border-gray-200 px-2 py-1.5 dark:border-gray-800"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-medium text-gray-900 dark:text-gray-100">
                  {session.display_name || session.device_id}
                </div>
                <div className="truncate text-gray-500 dark:text-gray-400">
                  {session.source_types.join(', ') || session.state}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void revokeSession(session.session_id)}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                aria-label={`Revoke ${session.display_name || session.device_id}`}
                title="Revoke device"
              >
                <Unplug className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <PhoneSourcePreview
              apiUrl={apiUrl}
              workspaceId={workspaceId}
              session={session}
            />
          </div>
        ))}
      </div>

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

        <div
          className={`rounded border p-2 text-xs ${
            target.enabled
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200'
              : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
          }`}
          data-testid="motion-practice-readiness"
        >
          {target.readinessLabel}
        </div>

        {practiceError ? (
          <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
            {practiceError}
          </div>
        ) : null}

        {practiceResult ? (
          <div className="space-y-1 rounded border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">
            <div>Submitted: {practiceResult.status}</div>
            <div className="break-all font-mono">meeting {practiceResult.meetingId}</div>
            <div className="break-all font-mono">command {practiceResult.commandId}</div>
            {practiceResult.liveSessionId ? (
              <div className="break-all font-mono">motion {practiceResult.liveSessionId}</div>
            ) : null}
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => void startPractice()}
          disabled={!selectedSession || !target.enabled || practiceState === 'starting'}
          className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-500 dark:disabled:bg-gray-800 dark:disabled:text-gray-500"
          data-testid="motion-practice-start-button"
        >
          {practiceState === 'starting'
            ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            : <PlayCircle className="h-4 w-4" aria-hidden="true" />}
          Start practice
        </button>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => void copyPracticeCommand()}
            disabled={!practiceCommandPreview}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
          >
            Copy command
          </button>
          <a
            href={`/workspaces/${encodeURIComponent(workspaceId)}/meetings${practiceResult ? `?session_id=${encodeURIComponent(practiceResult.meetingId)}` : ''}`}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-center text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
          >
            Records
          </a>
        </div>
      </div>

      <button
        type="button"
        onClick={() => void startPairing()}
        disabled={disabled || state === 'creating'}
        className="mt-auto inline-flex w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-wait disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
      >
        {state === 'creating' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
        New pairing code
      </button>
    </div>
  );
}

export default MotionSourceRailPanel;

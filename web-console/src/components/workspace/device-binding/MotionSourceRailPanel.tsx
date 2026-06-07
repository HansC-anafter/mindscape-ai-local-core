'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link2, Loader2, MonitorUp, Smartphone, Unplug } from 'lucide-react';

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
  assessDeviceLinkOriginReadiness,
  resolveDeviceLinkPublicOrigin,
} from '@/lib/media-transport/deviceLinkReadiness';
import { createQrCodeSvgPath } from '@/lib/media-transport/qrCode';
import { MotionPracticeRailController } from './practice/MotionPracticeRailController';
import type { MotionPracticeLaunchResult } from './motionPracticeLauncher';
import type { MotionPracticeWindowAppendEvent } from './practice/MotionPracticeLiveGuidancePanel';

interface MotionSourceRailPanelProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
}

type PanelState = 'idle' | 'creating' | 'pairing' | 'connected' | 'error';

function sortSessions(sessions: DeviceSessionEntry[]): DeviceSessionEntry[] {
  return [...sessions].sort((left, right) => left.created_at_epoch - right.created_at_epoch);
}

type DeviceLinkSourceMode = 'phone' | 'camera';

function buildDeviceLink(
  pairing: DevicePairingCode | null,
  workspaceId: string,
  sourceMode: DeviceLinkSourceMode,
  publicOrigin?: string,
): string {
  if (!pairing) {
    return '';
  }
  const fallbackPath = `${pairing.device_link_path}?workspaceId=${encodeURIComponent(workspaceId)}&sourceMode=${sourceMode}`;
  if (typeof window === 'undefined') {
    return `${pairing.device_link_path}?workspaceId=${encodeURIComponent(workspaceId)}&sourceMode=${sourceMode}`;
  }
  const origin = publicOrigin?.trim() || window.location.origin;
  let url: URL;
  try {
    url = new URL(pairing.device_link_path, origin);
  } catch {
    return fallbackPath;
  }
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
  const [practiceResult, setPracticeResult] = useState<MotionPracticeLaunchResult | null>(null);
  const [latestWindowAppend, setLatestWindowAppend] =
    useState<MotionPracticeWindowAppendEvent | null>(null);
  const [phonePublicOrigin, setPhonePublicOrigin] = useState('');
  const socketRef = useRef<DeviceControlSocket | null>(null);

  useEffect(() => () => socketRef.current?.close(), []);

  const fallbackBrowserOrigin = typeof window === 'undefined' ? '' : window.location.origin;
  const phoneOrigin = useMemo(() => resolveDeviceLinkPublicOrigin({
    overrideOrigin: phonePublicOrigin,
    fallbackOrigin: fallbackBrowserOrigin,
  }), [fallbackBrowserOrigin, phonePublicOrigin]);
  const phoneReadiness = useMemo(
    () => assessDeviceLinkOriginReadiness(phoneOrigin),
    [phoneOrigin],
  );
  const phoneDeviceLink = useMemo(() => (
    buildDeviceLink(pairing, workspaceId, 'phone', phoneOrigin)
  ), [pairing, phoneOrigin, workspaceId]);
  const phoneQrCode = useMemo(() => {
    if (!phoneReadiness.qrReady || !phoneDeviceLink) {
      return null;
    }
    try {
      return createQrCodeSvgPath(phoneDeviceLink);
    } catch {
      return null;
    }
  }, [phoneDeviceLink, phoneReadiness.qrReady]);
  const desktopDeviceLink = useMemo(() => (
    buildDeviceLink(pairing, workspaceId, 'camera')
  ), [pairing, workspaceId]);
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
            <label className="mt-2 block">
              <span className="mb-1 block text-[10px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
                Phone HTTPS origin
              </span>
              <input
                value={phonePublicOrigin}
                onChange={(event) => setPhonePublicOrigin(event.target.value)}
                placeholder="https://192.168.x.x:8343"
                className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-[11px] text-gray-900 placeholder:text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                data-testid="phone-public-origin-input"
              />
            </label>
            <div
              className={`mt-2 rounded border px-2 py-1 text-[11px] ${
                phoneReadiness.state === 'ready'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200'
                  : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
              }`}
              data-testid="phone-lan-readiness"
            >
              {phoneReadiness.message}
            </div>
            <div
              className="mt-2 rounded border border-gray-200 px-2 py-1 text-[11px] text-gray-600 dark:border-gray-800 dark:text-gray-300"
              data-testid="phone-qr-readiness"
            >
              {phoneReadiness.qrReady
                ? 'QR-ready link: open this HTTPS link on the phone.'
                : 'QR blocked until a non-localhost HTTPS origin is configured.'}
            </div>
            {phoneQrCode ? (
              <div
                className="mt-2 flex justify-center rounded border border-gray-200 bg-white p-2 text-gray-950 dark:border-gray-800"
                data-testid="phone-qr-code"
              >
                <svg
                  role="img"
                  aria-label="Phone pairing QR code"
                  viewBox={`0 0 ${phoneQrCode.viewBoxSize} ${phoneQrCode.viewBoxSize}`}
                  className="h-36 w-36"
                  shapeRendering="crispEdges"
                >
                  <path d={phoneQrCode.path} fill="currentColor" />
                </svg>
              </div>
            ) : null}
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
              liveMotionSessionId={
                practiceResult?.sourceSessionId === session.session_id
                  ? practiceResult.liveSessionId
                  : null
              }
              onMotionWindowAppended={setLatestWindowAppend}
            />
          </div>
        ))}
      </div>

      <MotionPracticeRailController
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        sessions={sessions}
        result={practiceResult}
        latestWindowAppend={latestWindowAppend}
        onResultChange={setPracticeResult}
      />

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

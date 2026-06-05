'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link2, Loader2, Smartphone, Unplug, X } from 'lucide-react';

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

interface DeviceBindingPanelProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
}

type PanelState = 'idle' | 'creating' | 'pairing' | 'connected' | 'error';

function sortSessions(sessions: DeviceSessionEntry[]): DeviceSessionEntry[] {
  return [...sessions].sort((left, right) => left.created_at_epoch - right.created_at_epoch);
}

export function DeviceBindingPanel({
  apiUrl,
  workspaceId,
  disabled = false,
}: DeviceBindingPanelProps) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<PanelState>('idle');
  const [pairing, setPairing] = useState<DevicePairingCode | null>(null);
  const [sessions, setSessions] = useState<DeviceSessionEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<DeviceControlSocket | null>(null);

  useEffect(() => () => socketRef.current?.close(), []);

  const deviceLink = useMemo(() => {
    if (!pairing || typeof window === 'undefined') {
      if (!pairing) {
        return '';
      }
      return `${pairing.device_link_path}?workspaceId=${encodeURIComponent(workspaceId)}`;
    }
    const url = new URL(pairing.device_link_path, window.location.origin);
    url.searchParams.set('workspaceId', workspaceId);
    return url.toString();
  }, [pairing, workspaceId]);

  const applyEvent = (event: DeviceControlEvent) => {
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
  };

  const startPairing = async () => {
    if (disabled || state === 'creating') {
      return;
    }
    setOpen(true);
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
  };

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
    <span className="relative inline-flex">
      <button
        type="button"
        onClick={() => {
          if (open) {
            setOpen(false);
            return;
          }
          setOpen(true);
          if (!pairing) {
            void startPairing();
          }
        }}
        disabled={disabled}
        className={`inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${sessions.length
          ? 'bg-sky-100 text-sky-700 hover:bg-sky-200 dark:bg-sky-900/40 dark:text-sky-200'
          : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
          } disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400 dark:disabled:bg-gray-800 dark:disabled:text-gray-500`}
        aria-label="Bind motion source device"
        title="Bind motion source device"
      >
        <Smartphone className="h-4 w-4" aria-hidden="true" />
      </button>

      {open ? (
        <div className="absolute bottom-11 left-0 z-50 w-80 rounded-lg border border-gray-200 bg-white p-3 text-xs shadow-xl dark:border-gray-700 dark:bg-gray-900">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="font-semibold text-gray-900 dark:text-gray-100">Motion source</div>
              <div className="truncate text-gray-500 dark:text-gray-400" data-testid="device-binding-state">
                {state}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
              aria-label="Close device binding panel"
              title="Close"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          {pairing ? (
            <div className="mb-3 rounded-md border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-800">
              <div className="mb-1 flex items-center gap-1 font-mono text-sm font-semibold text-gray-900 dark:text-gray-100">
                <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
                {pairing.pairing_code}
              </div>
              <a
                href={deviceLink}
                target="_blank"
                rel="noreferrer"
                className="block truncate text-sky-700 hover:text-sky-800 dark:text-sky-300"
              >
                {deviceLink}
              </a>
            </div>
          ) : null}

          {error ? (
            <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-2 py-1.5 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
              {error}
            </div>
          ) : null}

          <div className="space-y-2">
            {sessions.map((session) => (
              <div
                key={session.session_id}
                className="rounded-md border border-gray-200 px-2 py-1.5 dark:border-gray-700"
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

          <button
            type="button"
            onClick={() => void startPairing()}
            disabled={disabled || state === 'creating'}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-wait disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            {state === 'creating' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            New pairing code
          </button>
        </div>
      ) : null}
    </span>
  );
}

export default DeviceBindingPanel;

'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Camera, CheckCircle2, Loader2, XCircle } from 'lucide-react';

import {
  openDeviceControlSocket,
  type DeviceControlEvent,
  type DeviceControlSocket,
} from '@/lib/device-binding/deviceBindingClient';
import { getApiBaseUrl } from '@/lib/api-url';

interface DeviceLinkPageClientProps {
  pairingCode: string;
  workspaceId?: string;
}

type LinkState = 'idle' | 'connecting' | 'paired' | 'closed' | 'error';

function buildDeviceId(): string {
  const storageKey = 'mindscape_device_binding_id';
  if (typeof window === 'undefined') {
    return 'device_browser';
  }
  const existing = window.localStorage.getItem(storageKey);
  if (existing) {
    return existing;
  }
  const next = `browser_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  window.localStorage.setItem(storageKey, next);
  return next;
}

export function DeviceLinkPageClient({
  pairingCode,
  workspaceId = 'default',
}: DeviceLinkPageClientProps) {
  const [state, setState] = useState<LinkState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const socketRef = useRef<DeviceControlSocket | null>(null);
  const apiUrl = useMemo(() => getApiBaseUrl(), []);

  useEffect(() => () => socketRef.current?.close(), []);

  const handleEvent = (event: DeviceControlEvent) => {
    if (event.type === 'session_paired' || event.type === 'heartbeat_ack') {
      setState('paired');
      setMessage(event.display_name || event.device_id || 'paired');
      return;
    }
    if (event.type === 'session_revoked' || event.type === 'session_closed' || event.type === 'session_expired') {
      setState('closed');
      setMessage(event.reason || event.type);
      return;
    }
    if (event.type === 'session_error' || event.type === 'session_rejected') {
      setState('error');
      setMessage(event.reason || event.message || 'device_link_error');
    }
  };

  const connect = () => {
    if (state === 'connecting' || state === 'paired') {
      return;
    }
    setState('connecting');
    setMessage(null);
    socketRef.current?.close();
    const socket = openDeviceControlSocket({
      apiBase: apiUrl,
      workspaceId,
      pairingCode,
      onOpen: () => {
        socket.send({
          type: 'source_join',
          device_id: buildDeviceId(),
          display_name: 'Browser device',
          source_types: ['phone_camera', 'microphone'],
          metadata: {
            user_agent: typeof navigator === 'undefined' ? 'unknown' : navigator.userAgent,
          },
        });
      },
      onEvent: handleEvent,
      onError: (error) => {
        setState('error');
        setMessage(error.message);
      },
      onClose: () => {
        setState((current) => (current === 'paired' ? 'closed' : current));
      },
    });
    socketRef.current = socket;
  };

  const statusIcon = state === 'paired'
    ? <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden="true" />
    : state === 'error' || state === 'closed'
      ? <XCircle className="h-5 w-5 text-red-500" aria-hidden="true" />
      : <Camera className="h-5 w-5 text-sky-500" aria-hidden="true" />;

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100">
      <div className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-5">
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-5 shadow-2xl">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-800">
              {statusIcon}
            </div>
            <div className="min-w-0">
              <h1 className="text-lg font-semibold">Motion source</h1>
              <p className="truncate text-sm text-gray-400">{state}</p>
            </div>
          </div>

          <div className="mb-5 rounded-md border border-gray-800 bg-gray-950 px-3 py-2 font-mono text-sm">
            {pairingCode}
          </div>

          {message ? (
            <div className="mb-5 rounded-md border border-gray-800 bg-gray-950 px-3 py-2 text-sm text-gray-300">
              {message}
            </div>
          ) : null}

          <button
            type="button"
            onClick={connect}
            disabled={state === 'connecting' || state === 'paired'}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-sky-500 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
          >
            {state === 'connecting' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            Connect
          </button>
        </div>
      </div>
    </main>
  );
}

export default DeviceLinkPageClient;

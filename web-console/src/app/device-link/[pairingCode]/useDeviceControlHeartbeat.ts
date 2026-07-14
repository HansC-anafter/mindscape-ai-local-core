'use client';

import { useEffect, type RefObject } from 'react';

import type { DeviceControlSocket } from '@/lib/device-binding/deviceBindingClient';
import { isActiveLinkState } from './useDeviceLinkCaptureSessionHelpers';
import type { LinkState } from './useDeviceLinkCaptureSessionTypes';

const DEVICE_CONTROL_HEARTBEAT_INTERVAL_MS = 30_000;

interface DeviceControlHeartbeatInput {
  deviceSessionId: string | null;
  socketRef: RefObject<DeviceControlSocket | null>;
  state: LinkState;
}

export function useDeviceControlHeartbeat({
  deviceSessionId,
  socketRef,
  state,
}: DeviceControlHeartbeatInput) {
  useEffect(() => {
    if (!deviceSessionId || !isActiveLinkState(state)) {
      return undefined;
    }
    const heartbeatId = window.setInterval(() => {
      socketRef.current?.send({ type: 'heartbeat' });
    }, DEVICE_CONTROL_HEARTBEAT_INTERVAL_MS);
    return () => window.clearInterval(heartbeatId);
  }, [deviceSessionId, socketRef, state]);
}

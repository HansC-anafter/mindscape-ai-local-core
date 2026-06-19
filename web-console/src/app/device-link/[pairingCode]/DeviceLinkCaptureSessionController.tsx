'use client';

import React, { useEffect, useState } from 'react';

import { MobileCaptureCockpit } from './MobileCaptureCockpit';
import { PadCaptureCompanion } from './PadCaptureCompanion';
import {
  useDeviceLinkCaptureSession,
  type SourceMode,
} from './useDeviceLinkCaptureSession';

interface DeviceLinkCaptureSessionControllerProps {
  pairingCode: string;
  workspaceId: string;
  initialSourceMode?: SourceMode;
}

function readWideLayout(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(min-width: 900px)').matches;
}

export function DeviceLinkCaptureSessionController({
  pairingCode,
  workspaceId,
  initialSourceMode = 'phone',
}: DeviceLinkCaptureSessionControllerProps) {
  const session = useDeviceLinkCaptureSession({
    pairingCode,
    workspaceId,
    initialSourceMode,
  });
  const [wideLayout, setWideLayout] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const query = window.matchMedia('(min-width: 900px)');
    const update = () => setWideLayout(query.matches);
    update();
    query.addEventListener?.('change', update);
    return () => {
      query.removeEventListener?.('change', update);
    };
  }, []);

  return wideLayout ? (
    <PadCaptureCompanion session={session} />
  ) : (
    <MobileCaptureCockpit session={session} />
  );
}

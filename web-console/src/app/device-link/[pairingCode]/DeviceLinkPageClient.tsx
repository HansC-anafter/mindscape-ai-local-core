'use client';

import React from 'react';

import { DeviceLinkCaptureSessionController } from './DeviceLinkCaptureSessionController';
import type { SourceMode } from './useDeviceLinkCaptureSession';

interface DeviceLinkPageClientProps {
  pairingCode: string;
  workspaceId?: string;
  initialSourceMode?: SourceMode;
}

export function DeviceLinkPageClient({
  pairingCode,
  workspaceId = 'default',
  initialSourceMode = 'phone',
}: DeviceLinkPageClientProps) {
  return (
    <DeviceLinkCaptureSessionController
      pairingCode={pairingCode}
      workspaceId={workspaceId}
      initialSourceMode={initialSourceMode}
    />
  );
}

export default DeviceLinkPageClient;

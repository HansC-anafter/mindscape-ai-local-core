'use client';

import React from 'react';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import { PhoneSourcePreview } from '../PhoneSourcePreview';

interface CaptureSourcePreviewProps {
  apiUrl: string;
  workspaceId: string;
  session: DeviceSessionEntry;
}

export function CaptureSourcePreview({
  apiUrl,
  workspaceId,
  session,
}: CaptureSourcePreviewProps) {
  return (
    <PhoneSourcePreview
      apiUrl={apiUrl}
      workspaceId={workspaceId}
      session={session}
    />
  );
}

export default CaptureSourcePreview;

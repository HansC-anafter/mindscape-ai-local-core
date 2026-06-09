'use client';

import React from 'react';

import { CaptureSourceRail } from './capture-bridge/CaptureSourceRail';

interface MotionSourceRailPanelProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
}

export function MotionSourceRailPanel({
  apiUrl,
  workspaceId,
  disabled = false,
}: MotionSourceRailPanelProps) {
  return React.createElement(CaptureSourceRail, {
    apiUrl,
    workspaceId,
    disabled,
  });
}

export default MotionSourceRailPanel;

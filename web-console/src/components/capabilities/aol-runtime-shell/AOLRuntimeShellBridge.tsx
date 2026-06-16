'use client';

import React, { useContext, useEffect, useMemo, useRef } from 'react';

import type { AddressableObjectHostBridge } from '@/lib/addressable-object-layer';
import {
  AOLRuntimeShellContext,
  type AOLRuntimeShellProps,
  type AOLRuntimeSurfaceContext,
} from './AOLRuntimeShellContext';

const NOOP_HOST_BRIDGE: AddressableObjectHostBridge = {
  mode: 'idle',
  selection: null,
  graphSelection: null,
  currentMeetingId: null,
  requestObjectTargeting: () => {},
  cancelObjectTargeting: () => {},
  onSelectObject: () => {},
  onSelectGraph: () => {},
  clearCurrentObject: () => {},
  openCurrentMeeting: () => {},
};

export function AOLRuntimeShellBridge({
  apiUrl,
  workspaceId,
  capabilityCode,
  route,
  surfaceId,
  children,
}: AOLRuntimeShellProps) {
  const controller = useContext(AOLRuntimeShellContext);
  const registrationIdRef = useRef<string | null>(null);
  const activateSurface = controller?.activateSurface;
  const deactivateSurface = controller?.deactivateSurface;

  if (!registrationIdRef.current) {
    registrationIdRef.current = `aol-surface-${Math.random().toString(36).slice(2)}`;
  }

  const surfaceContext = useMemo<AOLRuntimeSurfaceContext>(
    () => ({
      apiUrl,
      workspaceId,
      capabilityCode,
      route,
      surfaceId,
    }),
    [apiUrl, workspaceId, capabilityCode, route, surfaceId],
  );

  useEffect(() => {
    if (!activateSurface || !deactivateSurface) {
      return undefined;
    }
    const registrationId = registrationIdRef.current;
    if (!registrationId) {
      return undefined;
    }
    activateSurface(surfaceContext, registrationId);
    return () => {
      deactivateSurface(surfaceContext, registrationId);
    };
  }, [activateSurface, deactivateSurface, surfaceContext]);

  if (!controller) {
    return <>{children(NOOP_HOST_BRIDGE)}</>;
  }

  const hostBridge = useMemo<AddressableObjectHostBridge>(
    () => ({
      mode: controller.state.mode,
      selection: controller.state.selection,
      graphSelection: controller.state.graphSelection,
      currentMeetingId: controller.state.currentMeetingId,
      requestObjectTargeting: controller.requestObjectTargeting,
      cancelObjectTargeting: controller.cancelObjectTargeting,
      onSelectObject: (selection) => controller.captureSelection(surfaceContext, selection),
      onSelectGraph: (selection) => controller.captureGraphSelection(surfaceContext, selection),
      clearCurrentObject: controller.clearCurrentObject,
      openCurrentMeeting: controller.openCurrentMeeting,
    }),
    [
      controller.captureGraphSelection,
      controller.captureSelection,
      controller.cancelObjectTargeting,
      controller.clearCurrentObject,
      controller.openCurrentMeeting,
      controller.requestObjectTargeting,
      controller.state.currentMeetingId,
      controller.state.graphSelection,
      controller.state.mode,
      controller.state.selection,
      surfaceContext,
    ],
  );

  return <>{children(hostBridge)}</>;
}

export default AOLRuntimeShellBridge;

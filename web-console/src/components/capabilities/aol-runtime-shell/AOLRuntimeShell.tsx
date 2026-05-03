'use client';

import { useContext, useEffect, useMemo, useRef } from 'react';

import type { AddressableObjectHostBridge } from '@/lib/addressable-object-layer';
import {
  AOLRuntimeShellContext,
  type AOLRuntimeShellController,
  type AOLRuntimeShellProps,
  type AOLRuntimeSurfaceContext,
} from './AOLRuntimeShellContext';
import { AOLRuntimeShellProviderImpl } from './AOLRuntimeShellProviderImpl';
import { buildCapabilitySurfaceId } from './runtimeShellState';

function AOLRuntimeShellBridgeSlot({
  apiUrl,
  workspaceId,
  capabilityCode,
  route,
  surfaceId,
  children,
}: AOLRuntimeShellProps) {
  const controller = useContext(AOLRuntimeShellContext);
  const registrationIdRef = useRef<string | null>(null);

  if (!controller) {
    throw new Error('AOLRuntimeShellBridgeSlot requires AOLRuntimeShellProvider.');
  }

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
    const registrationId = registrationIdRef.current;
    if (!registrationId) {
      return;
    }
    controller.activateSurface(surfaceContext, registrationId);
    return () => {
      controller.deactivateSurface(surfaceContext, registrationId);
    };
  }, [controller.activateSurface, controller.deactivateSurface, surfaceContext]);

  const hostBridge = useMemo<AddressableObjectHostBridge>(
    () => ({
      mode: controller.state.mode,
      selection: controller.state.selection,
      currentMeetingId: controller.state.currentMeetingId,
      requestObjectTargeting: controller.requestObjectTargeting,
      cancelObjectTargeting: controller.cancelObjectTargeting,
      onSelectObject: (selection) => controller.captureSelection(surfaceContext, selection),
      clearCurrentObject: controller.clearCurrentObject,
      openCurrentMeeting: controller.openCurrentMeeting,
    }),
    [
      controller.captureSelection,
      controller.cancelObjectTargeting,
      controller.clearCurrentObject,
      controller.openCurrentMeeting,
      controller.requestObjectTargeting,
      controller.state.currentMeetingId,
      controller.state.mode,
      controller.state.selection,
      surfaceContext,
    ],
  );

  return <>{children(hostBridge)}</>;
}

export const AOLRuntimeShellProvider = AOLRuntimeShellProviderImpl;

export function AOLRuntimeShell(props: AOLRuntimeShellProps) {
  const existingController = useContext(AOLRuntimeShellContext);

  if (existingController) {
    return <AOLRuntimeShellBridgeSlot {...props} />;
  }

  return (
    <AOLRuntimeShellProvider workspaceId={props.workspaceId}>
      <AOLRuntimeShellBridgeSlot {...props} />
    </AOLRuntimeShellProvider>
  );
}

export function useAOLRuntimeShellController(): AOLRuntimeShellController | null {
  return useContext(AOLRuntimeShellContext);
}

export type {
  AOLRuntimeShellController,
  AOLRuntimeShellProps,
  AOLRuntimeShellProviderProps,
  AOLRuntimeShellState,
  AOLRuntimeSurfaceContext,
  RegisteredRuntimeSurfaceContext,
} from './AOLRuntimeShellContext';

export { buildCapabilitySurfaceId };

export default AOLRuntimeShell;

'use client';

import React, { useContext } from 'react';

import {
  AOLRuntimeShellContext,
  type AOLRuntimeShellController,
  type AOLRuntimeShellProps,
} from './AOLRuntimeShellContext';
import { AOLRuntimeShellBridge } from './AOLRuntimeShellBridge';
import { AOLRuntimeShellProviderImpl } from './AOLRuntimeShellProviderImpl';
import { buildCapabilitySurfaceId } from './runtimeShellState';

export const AOLRuntimeShellProvider = AOLRuntimeShellProviderImpl;

export function AOLRuntimeShell(props: AOLRuntimeShellProps) {
  const existingController = useContext(AOLRuntimeShellContext);

  if (existingController) {
    return <AOLRuntimeShellBridge {...props} />;
  }

  return (
    <AOLRuntimeShellProvider workspaceId={props.workspaceId}>
      <AOLRuntimeShellBridge {...props} />
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

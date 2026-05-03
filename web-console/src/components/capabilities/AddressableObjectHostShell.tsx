'use client';

export {
  AOLRuntimeShell as AddressableObjectHostShell,
  AOLRuntimeShellProvider as AddressableObjectHostProvider,
  buildCapabilitySurfaceId,
  useAOLRuntimeShellController as useAddressableObjectHostController,
} from './aol-runtime-shell/AOLRuntimeShell';

export type {
  AOLRuntimeShellController as AddressableObjectHostController,
  AOLRuntimeShellProps as AddressableObjectHostShellProps,
  AOLRuntimeShellProviderProps as AddressableObjectHostProviderProps,
  AOLRuntimeShellState as AOLPanelState,
  AOLRuntimeSurfaceContext as AddressableObjectSurfaceContext,
  RegisteredRuntimeSurfaceContext as RegisteredSurfaceContext,
} from './aol-runtime-shell/AOLRuntimeShellContext';

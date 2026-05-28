'use client';

import { createContext, type ReactNode } from 'react';

import type {
  AddressableObjectHostBridge,
  AddressableObjectHostMode,
  AddressableObjectRole,
  AddressableRuntimeError,
  AddressableSelectionCandidate,
  AddressableSelectionTarget,
  ObjectMeetingAttachResponse,
  ResolvedAddressableObject,
} from '@/lib/addressable-object-layer';

export type AOLRuntimeSurfaceContext = {
  apiUrl: string;
  workspaceId: string;
  capabilityCode: string;
  route: string;
  surfaceId: string;
};

export interface RegisteredRuntimeSurfaceContext extends AOLRuntimeSurfaceContext {
  registrationId: string;
}

export interface AOLRuntimeShellState {
  mode: AddressableObjectHostMode;
  activeSurface: AOLRuntimeSurfaceContext | null;
  selection: AddressableSelectionTarget | null;
  contextRole: AddressableObjectRole;
  resolvedObject: ResolvedAddressableObject | null;
  candidateObjects: AddressableSelectionCandidate[];
  warnings: AddressableRuntimeError[];
  attachResponse: ObjectMeetingAttachResponse | null;
  currentMeetingId: string | null;
  error: string | null;
}

export interface AOLRuntimeShellProps extends AOLRuntimeSurfaceContext {
  children: (hostBridge: AddressableObjectHostBridge) => ReactNode;
}

export interface AOLRuntimeShellProviderProps {
  workspaceId: string;
  children: ReactNode;
}

export interface AOLRuntimeShellController {
  state: AOLRuntimeShellState;
  activateSurface: (surface: AOLRuntimeSurfaceContext, registrationId: string) => void;
  deactivateSurface: (surface: AOLRuntimeSurfaceContext, registrationId: string) => void;
  requestObjectTargeting: () => void;
  cancelObjectTargeting: () => void;
  clearCurrentObject: () => void;
  openCurrentMeeting: () => void;
  closeCurrentMeeting: () => void;
  captureSelection: (
    surface: AOLRuntimeSurfaceContext,
    selection: AddressableSelectionTarget,
  ) => Promise<void>;
  attachCurrentObject: () => Promise<void>;
}

export const IDLE_RUNTIME_SHELL_STATE: AOLRuntimeShellState = {
  mode: 'idle',
  activeSurface: null,
  selection: null,
  contextRole: 'source',
  resolvedObject: null,
  candidateObjects: [],
  warnings: [],
  attachResponse: null,
  currentMeetingId: null,
  error: null,
};

export const AOLRuntimeShellContext = createContext<AOLRuntimeShellController | null>(null);

export type AddressableObjectSurfaceContext = AOLRuntimeSurfaceContext;
export type RegisteredSurfaceContext = RegisteredRuntimeSurfaceContext;
export type AOLPanelState = AOLRuntimeShellState;
export type AddressableObjectHostShellProps = AOLRuntimeShellProps;
export type AddressableObjectHostProviderProps = AOLRuntimeShellProviderProps;
export type AddressableObjectHostController = AOLRuntimeShellController;
export const IDLE_PANEL_STATE = IDLE_RUNTIME_SHELL_STATE;
export const AddressableObjectHostContext = AOLRuntimeShellContext;

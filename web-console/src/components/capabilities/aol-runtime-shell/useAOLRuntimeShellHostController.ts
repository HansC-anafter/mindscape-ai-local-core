'use client';

import { useCallback, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react';

import {
  attachAddressableObjectToMeeting,
  resolveAddressableSelection,
  type AddressableGraphSelection,
  type AddressableObjectRole,
  type AddressableSelectionCandidate,
  type AddressableSelectionTarget,
} from '@/lib/addressable-object-layer';
import {
  IDLE_RUNTIME_SHELL_STATE,
  type AOLRuntimeShellController,
  type AOLRuntimeShellState,
  type AOLRuntimeSurfaceContext,
} from './AOLRuntimeShellContext';
import { type MeetingPaneSizePreset } from './RuntimeShellPanel';
import {
  buildSelectingState,
  canAttachCurrentObjectToMeeting,
} from './runtimeShellState';
import { useAOLRuntimeSurfaceRegistry } from './useAOLRuntimeSurfaceRegistry';
import { useRuntimeShellMeetingPaneSizing } from './useRuntimeShellMeetingPaneSizing';

export interface AOLRuntimeShellHostController {
  shellRootRef: RefObject<HTMLDivElement | null>;
  panelState: AOLRuntimeShellState;
  meetingPaneHeight: number;
  canOpenFlow: boolean;
  controller: AOLRuntimeShellController;
  requestObjectTargeting: () => void;
  cancelObjectTargeting: () => void;
  clearCurrentObject: () => void;
  attachCurrentObject: () => Promise<void>;
  openCurrentMeeting: () => void;
  closeCurrentMeeting: () => void;
  changeContextRole: (role: AddressableObjectRole) => void;
  selectCandidateObject: (candidate: AddressableSelectionCandidate) => void;
  beginMeetingPaneResize: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  setMeetingPaneSizePreset: (preset: MeetingPaneSizePreset) => void;
  openRuntimeFlowFromRail: () => void;
}

export function useAOLRuntimeShellHostController(): AOLRuntimeShellHostController {
  const [panelState, setPanelState] = useState<AOLRuntimeShellState>(IDLE_RUNTIME_SHELL_STATE);
  const requestEpochRef = useRef(0);
  const {
    activateSurface,
    deactivateSurface,
  } = useAOLRuntimeSurfaceRegistry({ setPanelState });
  const {
    shellRootRef: shellRootSizingRef,
    meetingPaneHeight,
    beginMeetingPaneResize,
    setMeetingPaneSizePreset,
  } = useRuntimeShellMeetingPaneSizing(panelState.mode === 'meeting_opened');

  const invalidateInflightRequests = useCallback(() => {
    requestEpochRef.current += 1;
    return requestEpochRef.current;
  }, []);

  const requestObjectTargeting = useCallback(() => {
    invalidateInflightRequests();
    setPanelState((current) => buildSelectingState(current.activeSurface, current.contextRole));
  }, [invalidateInflightRequests]);

  const cancelObjectTargeting = useCallback(() => {
    invalidateInflightRequests();
    setPanelState((current) => ({
      ...IDLE_RUNTIME_SHELL_STATE,
      activeSurface: current.activeSurface,
      contextRole: current.contextRole,
    }));
  }, [invalidateInflightRequests]);

  const clearCurrentObject = useCallback(() => {
    invalidateInflightRequests();
    setPanelState((current) => ({
      ...IDLE_RUNTIME_SHELL_STATE,
      activeSurface: current.activeSurface,
      contextRole: current.contextRole,
    }));
  }, [invalidateInflightRequests]);

  const openCurrentMeeting = useCallback(() => {
    setPanelState((current) => {
      if (!current.currentMeetingId) {
        return current;
      }
      return {
        ...current,
        mode: 'meeting_opened',
        error: null,
      };
    });
  }, []);

  const closeCurrentMeeting = useCallback(() => {
    setPanelState((current) => {
      if (current.mode !== 'meeting_opened') {
        return current;
      }
      return {
        ...current,
        mode: current.resolvedObject ? 'selected' : 'idle',
      };
    });
  }, []);

  const captureSelectionWithGraph = useCallback(
    async (
      surface: AOLRuntimeSurfaceContext,
      selection: AddressableSelectionTarget,
      graphSelection: AddressableGraphSelection | null,
    ) => {
      const requestEpoch = invalidateInflightRequests();
      const contextRole = selection.role ?? panelState.contextRole ?? 'source';
      const roleSelection = {
        ...selection,
        role: contextRole,
      };
      setPanelState({
        mode: 'resolving',
        activeSurface: surface,
        selection: roleSelection,
        graphSelection,
        contextRole,
        resolvedObject: null,
        candidateObjects: [],
        warnings: [],
        attachResponse: null,
        currentMeetingId: null,
        error: null,
      });

      try {
        const response = await resolveAddressableSelection({
          apiUrl: surface.apiUrl,
          workspaceId: surface.workspaceId,
          capabilityCode: surface.capabilityCode,
          route: surface.route,
          surfaceId: surface.surfaceId,
          selection: roleSelection,
        });

        if (requestEpoch !== requestEpochRef.current) {
          return;
        }

        if (response.status === 'ambiguous' && response.candidate_objects.length > 0) {
          setPanelState({
            mode: 'disambiguating',
            activeSurface: surface,
            selection: roleSelection,
            graphSelection,
            contextRole,
            resolvedObject: null,
            candidateObjects: response.candidate_objects,
            warnings: response.errors,
            attachResponse: null,
            currentMeetingId: null,
            error: null,
          });
          return;
        }

        if (response.status !== 'resolved' || response.resolved_objects.length === 0) {
          setPanelState({
            mode: 'error',
            activeSurface: surface,
            selection: roleSelection,
            graphSelection,
            contextRole,
            resolvedObject: null,
            candidateObjects: response.candidate_objects,
            warnings: response.errors,
            attachResponse: null,
            currentMeetingId: null,
            error:
              response.errors[0]?.message ||
              (response.candidate_objects.length > 1
                ? 'Selection resolved to multiple candidates.'
                : 'Selection did not resolve to an addressable object.'),
          });
          return;
        }

        setPanelState({
          mode: 'selected',
          activeSurface: surface,
          selection: roleSelection,
          graphSelection,
          contextRole,
          resolvedObject: response.resolved_objects[0],
          candidateObjects: [],
          warnings: response.errors,
          attachResponse: null,
          currentMeetingId: null,
          error: null,
        });
      } catch (resolveError) {
        if (requestEpoch !== requestEpochRef.current) {
          return;
        }

        setPanelState({
          mode: 'error',
          activeSurface: surface,
          selection: roleSelection,
          graphSelection,
          contextRole,
          resolvedObject: null,
          candidateObjects: [],
          warnings: [],
          attachResponse: null,
          currentMeetingId: null,
          error:
            resolveError instanceof Error
              ? resolveError.message
              : 'Failed to resolve addressable object selection.',
        });
      }
    },
    [invalidateInflightRequests, panelState.contextRole],
  );

  const captureSelection = useCallback(
    async (surface: AOLRuntimeSurfaceContext, selection: AddressableSelectionTarget) => {
      await captureSelectionWithGraph(surface, selection, null);
    },
    [captureSelectionWithGraph],
  );

  const captureGraphSelection = useCallback(
    async (surface: AOLRuntimeSurfaceContext, graphSelection: AddressableGraphSelection) => {
      const anchor = graphSelection.anchors[0];
      if (!anchor) {
        invalidateInflightRequests();
        setPanelState({
          mode: 'selected',
          activeSurface: surface,
          selection: null,
          graphSelection,
          contextRole: panelState.contextRole,
          resolvedObject: null,
          candidateObjects: [],
          warnings: [],
          attachResponse: null,
          currentMeetingId: null,
          error: null,
        });
        return;
      }

      await captureSelectionWithGraph(surface, {
        ownerPack: anchor.owner_pack,
        objectKind: anchor.object_kind,
        objectId: anchor.object_id,
        selector: anchor.selector ?? anchor.ref?.selector ?? undefined,
        sourceSurface: anchor.source_surface ?? anchor.ref?.source_surface ?? graphSelection.source_surface,
        label: anchor.label ?? undefined,
        role: anchor.role ?? undefined,
      }, graphSelection);
    },
    [captureSelectionWithGraph, invalidateInflightRequests, panelState.contextRole],
  );

  const changeContextRole = useCallback((role: AddressableObjectRole) => {
    setPanelState((current) => ({
      ...current,
      contextRole: role,
      selection: current.selection
        ? {
            ...current.selection,
            role,
          }
        : current.selection,
    }));
  }, []);

  const selectCandidateObject = useCallback(
    (candidate: AddressableSelectionCandidate) => {
      const surface = panelState.activeSurface;
      if (!surface) {
        return;
      }

      void captureSelection(surface, {
        ownerPack: candidate.ref.owner_pack,
        objectKind: candidate.ref.object_kind,
        objectId: candidate.ref.object_id,
        version: candidate.ref.version ?? undefined,
        selector: candidate.ref.selector ?? undefined,
        sourceSurface:
          candidate.ref.source_surface ??
          panelState.selection?.sourceSurface ??
          surface.surfaceId,
        label: candidate.summary?.title ?? candidate.ref.object_id,
        role: panelState.contextRole,
      });
    },
    [
      captureSelection,
      panelState.activeSurface,
      panelState.contextRole,
      panelState.selection?.sourceSurface,
    ],
  );

  const attachCurrentObject = useCallback(async () => {
    const requestEpoch = invalidateInflightRequests();
    const stateSnapshot = panelState;

    if (!stateSnapshot.resolvedObject || !stateSnapshot.activeSurface) {
      return;
    }

    setPanelState((current) => ({
      ...current,
      mode: 'attaching',
      error: null,
      attachResponse: null,
    }));

    try {
      const response = await attachAddressableObjectToMeeting({
        apiUrl: stateSnapshot.activeSurface.apiUrl,
        workspaceId: stateSnapshot.activeSurface.workspaceId,
        resolvedObject: stateSnapshot.resolvedObject,
        role: stateSnapshot.contextRole,
      });

      if (requestEpoch !== requestEpochRef.current) {
        return;
      }

      if (response.status === 'rejected') {
        setPanelState((current) => ({
          ...current,
          mode: 'error',
          attachResponse: response,
          currentMeetingId: response.meeting_id || null,
          error: response.errors[0]?.message || 'Meeting attach was rejected.',
        }));
        return;
      }

      setPanelState((current) => ({
        ...current,
        mode: 'meeting_opened',
        attachResponse: response,
        currentMeetingId: response.meeting_id,
        error: null,
      }));
    } catch (attachError) {
      if (requestEpoch !== requestEpochRef.current) {
        return;
      }

      setPanelState((current) => ({
        ...current,
        mode: 'error',
        attachResponse: null,
        currentMeetingId: null,
        error:
          attachError instanceof Error ? attachError.message : 'Failed to attach object to meeting.',
      }));
    }
  }, [invalidateInflightRequests, panelState]);

  const openRuntimeFlowFromRail = useCallback(() => {
    if (panelState.mode === 'meeting_opened') {
      return;
    }
    if (panelState.currentMeetingId) {
      openCurrentMeeting();
      return;
    }
    if (canAttachCurrentObjectToMeeting(panelState)) {
      void attachCurrentObject();
      return;
    }
    if (panelState.activeSurface) {
      setPanelState((current) => ({
        ...current,
        mode: 'meeting_opened',
        error: null,
      }));
    }
  }, [attachCurrentObject, openCurrentMeeting, panelState]);

  const controller = useMemo<AOLRuntimeShellController>(
    () => ({
      state: panelState,
      activateSurface,
      deactivateSurface,
      requestObjectTargeting,
      cancelObjectTargeting,
      clearCurrentObject,
      openCurrentMeeting,
      closeCurrentMeeting,
      captureSelection,
      captureGraphSelection,
      attachCurrentObject,
    }),
    [
      panelState,
      activateSurface,
      deactivateSurface,
      requestObjectTargeting,
      cancelObjectTargeting,
      clearCurrentObject,
      openCurrentMeeting,
      closeCurrentMeeting,
      captureSelection,
      captureGraphSelection,
      attachCurrentObject,
    ],
  );

  return {
    shellRootRef: shellRootSizingRef,
    panelState,
    meetingPaneHeight,
    canOpenFlow:
      panelState.mode === 'meeting_opened' ||
      Boolean(panelState.currentMeetingId) ||
      canAttachCurrentObjectToMeeting(panelState) ||
      Boolean(panelState.activeSurface),
    controller,
    requestObjectTargeting,
    cancelObjectTargeting,
    clearCurrentObject,
    attachCurrentObject,
    openCurrentMeeting,
    closeCurrentMeeting,
    changeContextRole,
    selectCandidateObject,
    beginMeetingPaneResize,
    setMeetingPaneSizePreset,
    openRuntimeFlowFromRail,
  };
}

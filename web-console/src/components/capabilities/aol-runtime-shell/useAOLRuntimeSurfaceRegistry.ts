'use client';

import { useCallback, useRef, type Dispatch, type SetStateAction } from 'react';

import type {
  AOLRuntimeShellState,
  AOLRuntimeSurfaceContext,
  RegisteredRuntimeSurfaceContext,
} from './AOLRuntimeShellContext';
import { isSameSurface } from './runtimeShellState';

interface UseAOLRuntimeSurfaceRegistryArgs {
  setPanelState: Dispatch<SetStateAction<AOLRuntimeShellState>>;
}

interface AOLRuntimeSurfaceRegistry {
  activateSurface: (surface: AOLRuntimeSurfaceContext, registrationId: string) => void;
  deactivateSurface: (surface: AOLRuntimeSurfaceContext, registrationId: string) => void;
}

export function useAOLRuntimeSurfaceRegistry({
  setPanelState,
}: UseAOLRuntimeSurfaceRegistryArgs): AOLRuntimeSurfaceRegistry {
  const registeredSurfacesRef = useRef<RegisteredRuntimeSurfaceContext[]>([]);

  const activateSurface = useCallback((surface: AOLRuntimeSurfaceContext, registrationId: string) => {
    registeredSurfacesRef.current = [
      ...registeredSurfacesRef.current.filter((registeredSurface) => registeredSurface.registrationId !== registrationId),
      { ...surface, registrationId },
    ];
    setPanelState((current) => {
      const activeSurface = current.activeSurface;
      if (isSameSurface(activeSurface, surface)) {
        return current;
      }
      return {
        ...current,
        activeSurface: surface,
      };
    });
  }, [setPanelState]);

  const deactivateSurface = useCallback((surface: AOLRuntimeSurfaceContext, registrationId: string) => {
    registeredSurfacesRef.current = registeredSurfacesRef.current.filter(
      (registeredSurface) => registeredSurface.registrationId !== registrationId,
    );
    setPanelState((current) => {
      const activeSurface = current.activeSurface;
      if (!isSameSurface(activeSurface, surface)) {
        return current;
      }
      const fallbackRegisteredSurface =
        registeredSurfacesRef.current[registeredSurfacesRef.current.length - 1] ?? null;
      const fallbackSurface = fallbackRegisteredSurface
        ? {
            apiUrl: fallbackRegisteredSurface.apiUrl,
            workspaceId: fallbackRegisteredSurface.workspaceId,
            capabilityCode: fallbackRegisteredSurface.capabilityCode,
            route: fallbackRegisteredSurface.route,
            surfaceId: fallbackRegisteredSurface.surfaceId,
          }
        : null;
      return {
        ...current,
        activeSurface: fallbackSurface,
      };
    });
  }, [setPanelState]);

  return {
    activateSurface,
    deactivateSurface,
  };
}

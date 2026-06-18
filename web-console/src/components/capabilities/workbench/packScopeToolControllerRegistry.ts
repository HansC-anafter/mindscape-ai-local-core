'use client';

import React from 'react';

export const PACK_SCOPE_TOOL_CONTROLLER_EVENT = 'mindscape:pack-scope-tool-controller';

interface PackScopeToolControllerEventDetail {
  controllerKey: string;
}

declare global {
  interface Window {
    __mindscapePackScopeToolControllers?: Record<string, unknown>;
  }
}

function getPackScopeToolControllerRegistry(): Record<string, unknown> | null {
  if (typeof window === 'undefined') {
    return null;
  }
  if (!window.__mindscapePackScopeToolControllers) {
    window.__mindscapePackScopeToolControllers = {};
  }
  return window.__mindscapePackScopeToolControllers;
}

function dispatchPackScopeToolControllerEvent(controllerKey: string) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent<PackScopeToolControllerEventDetail>(PACK_SCOPE_TOOL_CONTROLLER_EVENT, {
    detail: { controllerKey },
  }));
}

export function readPackScopeToolController<T>(controllerKey: string): T | null {
  const registry = getPackScopeToolControllerRegistry();
  if (!registry) {
    return null;
  }
  return (registry[controllerKey] as T | undefined) ?? null;
}

export function useRegisterPackScopeToolController<T>(controllerKey: string, controller: T | null) {
  React.useLayoutEffect(() => {
    const registry = getPackScopeToolControllerRegistry();
    if (!registry) {
      return undefined;
    }
    if (controller === null) {
      delete registry[controllerKey];
    } else {
      registry[controllerKey] = controller;
    }
    dispatchPackScopeToolControllerEvent(controllerKey);
    return () => {
      if (registry[controllerKey] === controller) {
        delete registry[controllerKey];
        dispatchPackScopeToolControllerEvent(controllerKey);
      }
    };
  }, [controller, controllerKey]);
}

export function useOptionalPackScopeToolController<T>(controllerKey: string, contextController: T | null): T | null {
  const [globalController, setGlobalController] = React.useState<T | null>(() => readPackScopeToolController<T>(controllerKey));

  React.useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }
    const handleUpdate = (event?: Event) => {
      const detail = event instanceof CustomEvent
        ? (event.detail as PackScopeToolControllerEventDetail | undefined)
        : undefined;
      if (detail?.controllerKey && detail.controllerKey !== controllerKey) {
        return;
      }
      setGlobalController(readPackScopeToolController<T>(controllerKey));
    };
    handleUpdate();
    window.addEventListener(PACK_SCOPE_TOOL_CONTROLLER_EVENT, handleUpdate as EventListener);
    return () => window.removeEventListener(PACK_SCOPE_TOOL_CONTROLLER_EVENT, handleUpdate as EventListener);
  }, [controllerKey]);

  return contextController || globalController;
}

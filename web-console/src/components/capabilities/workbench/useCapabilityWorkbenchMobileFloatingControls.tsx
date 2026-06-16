'use client';

import React from 'react';

export interface CapabilityWorkbenchMobileFloatingControl {
  key: string;
  order: number;
  render: () => React.ReactNode;
}

export interface CapabilityWorkbenchMobileFloatingControlsContextValue {
  registerControls: (
    scopeId: string,
    controls: CapabilityWorkbenchMobileFloatingControl[],
  ) => () => void;
}

export const CapabilityWorkbenchMobileFloatingControlsContext =
  React.createContext<CapabilityWorkbenchMobileFloatingControlsContextValue | null>(null);

const CAPABILITY_WORKBENCH_MOBILE_FLOATING_CONTROLS_BRIDGE_EVENT =
  'mindscape:capability-workbench-mobile-floating-controls-bridge';

declare global {
  interface Window {
    __MindscapeCapabilityWorkbenchMobileFloatingControlsBridge?:
      CapabilityWorkbenchMobileFloatingControlsContextValue | null;
  }
}

function readGlobalCapabilityWorkbenchMobileFloatingControlsBridge():
CapabilityWorkbenchMobileFloatingControlsContextValue | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.__MindscapeCapabilityWorkbenchMobileFloatingControlsBridge || null;
}

function publishGlobalCapabilityWorkbenchMobileFloatingControlsBridge(
  value: CapabilityWorkbenchMobileFloatingControlsContextValue | null,
): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.__MindscapeCapabilityWorkbenchMobileFloatingControlsBridge = value;
  window.dispatchEvent(
    new CustomEvent(CAPABILITY_WORKBENCH_MOBILE_FLOATING_CONTROLS_BRIDGE_EVENT),
  );
}

export function useOptionalCapabilityWorkbenchMobileFloatingControls():
CapabilityWorkbenchMobileFloatingControlsContextValue | null {
  const context = React.useContext(CapabilityWorkbenchMobileFloatingControlsContext);
  const [bridge, setBridge] = React.useState<CapabilityWorkbenchMobileFloatingControlsContextValue | null>(() => (
    context || readGlobalCapabilityWorkbenchMobileFloatingControlsBridge()
  ));

  React.useEffect(() => {
    if (context) {
      setBridge(context);
      return undefined;
    }
    if (typeof window === 'undefined') {
      setBridge(null);
      return undefined;
    }
    const handleBridgeChange = () => {
      setBridge(readGlobalCapabilityWorkbenchMobileFloatingControlsBridge());
    };
    handleBridgeChange();
    window.addEventListener(
      CAPABILITY_WORKBENCH_MOBILE_FLOATING_CONTROLS_BRIDGE_EVENT,
      handleBridgeChange,
    );
    return () => {
      window.removeEventListener(
        CAPABILITY_WORKBENCH_MOBILE_FLOATING_CONTROLS_BRIDGE_EVENT,
        handleBridgeChange,
      );
    };
  }, [context]);

  return context || bridge;
}

export function useCapabilityWorkbenchMobileFloatingControlsRegistration(
  scopeId: string,
  controls: CapabilityWorkbenchMobileFloatingControl[],
): void {
  const bridge = useOptionalCapabilityWorkbenchMobileFloatingControls();

  React.useEffect(() => {
    if (!bridge) {
      return undefined;
    }
    return bridge.registerControls(scopeId, controls);
  }, [bridge, controls, scopeId]);
}

export function useCapabilityWorkbenchMobileFloatingControlsBridgePublisher(
  value: CapabilityWorkbenchMobileFloatingControlsContextValue | null,
): void {
  React.useEffect(() => {
    publishGlobalCapabilityWorkbenchMobileFloatingControlsBridge(value);
    return () => {
      if (readGlobalCapabilityWorkbenchMobileFloatingControlsBridge() === value) {
        publishGlobalCapabilityWorkbenchMobileFloatingControlsBridge(null);
      }
    };
  }, [value]);
}

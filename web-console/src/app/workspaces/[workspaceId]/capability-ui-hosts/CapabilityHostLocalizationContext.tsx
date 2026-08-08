'use client';

import React from 'react';

import type {
  CapabilityUiLocalizationBridgeV1,
} from '@/lib/capability-ui-localization';

interface CapabilityHostLocalizationContextValue {
  capabilityCode: string;
  localizationPromise: Promise<CapabilityUiLocalizationBridgeV1> | null;
}

const CapabilityHostLocalizationContext =
  React.createContext<CapabilityHostLocalizationContextValue | null>(null);

export function CapabilityHostLocalizationProvider({
  capabilityCode,
  localizationPromise,
  children,
}: CapabilityHostLocalizationContextValue & {
  children: React.ReactNode;
}) {
  const value = React.useMemo<CapabilityHostLocalizationContextValue>(() => ({
    capabilityCode,
    localizationPromise,
  }), [capabilityCode, localizationPromise]);

  return (
    <CapabilityHostLocalizationContext.Provider value={value}>
      {children}
    </CapabilityHostLocalizationContext.Provider>
  );
}

export function useCapabilityHostLocalizationPromise(
  capabilityCode: string | null | undefined,
): Promise<CapabilityUiLocalizationBridgeV1> | null {
  const context = React.useContext(CapabilityHostLocalizationContext);
  if (!capabilityCode || context?.capabilityCode !== capabilityCode) {
    return null;
  }
  return context.localizationPromise;
}

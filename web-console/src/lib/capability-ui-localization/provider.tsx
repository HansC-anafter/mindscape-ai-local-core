'use client';

import React, { createContext, useContext } from 'react';

import type {
  CapabilityUiLocalizationBridgeV1,
  CapabilityUiTranslationValues,
} from './contracts';

const CapabilityUiLocalizationContext =
  createContext<CapabilityUiLocalizationBridgeV1 | null>(null);

export function CapabilityUiLocalizationProvider({
  localization,
  children,
}: {
  localization: CapabilityUiLocalizationBridgeV1;
  children: React.ReactNode;
}) {
  return (
    <CapabilityUiLocalizationContext.Provider value={localization}>
      {children}
    </CapabilityUiLocalizationContext.Provider>
  );
}

export function useOptionalCapabilityLocalization(): CapabilityUiLocalizationBridgeV1 | null {
  return useContext(CapabilityUiLocalizationContext);
}

export function useCapabilityLocalization(): CapabilityUiLocalizationBridgeV1 {
  const localization = useOptionalCapabilityLocalization();
  if (!localization) {
    throw new Error(
      'useCapabilityLocalization must be used inside a localized capability entry',
    );
  }
  return localization;
}

export function useCapabilityT(): CapabilityUiLocalizationBridgeV1['t'] {
  return useCapabilityLocalization().t;
}

export function CapabilityMessage({
  id,
  values,
}: {
  id: string;
  values?: CapabilityUiTranslationValues;
}) {
  const t = useCapabilityT();
  return <>{t(id, values)}</>;
}

'use client';

import React, { createContext, useContext } from 'react';

import type {
  CapabilityUiLocalizationBridgeV1,
  CapabilityUiTranslationValues,
} from './contracts';

const GLOBAL_CONTEXT_KEY = '__mindscapeCapabilityUiLocalizationContextV1__';
type CapabilityUiLocalizationGlobal = typeof globalThis & {
  [GLOBAL_CONTEXT_KEY]?: React.Context<CapabilityUiLocalizationBridgeV1 | null>;
};
const localizationGlobal = globalThis as CapabilityUiLocalizationGlobal;
const CapabilityUiLocalizationContext =
  localizationGlobal[GLOBAL_CONTEXT_KEY]
  ?? createContext<CapabilityUiLocalizationBridgeV1 | null>(null);
localizationGlobal[GLOBAL_CONTEXT_KEY] = CapabilityUiLocalizationContext;

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

export function useCapabilityLocalization(): CapabilityUiLocalizationBridgeV1 {
  const localization = useContext(CapabilityUiLocalizationContext);
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

'use client';

import React from 'react';

import type {
  CapabilityUiLocalizationBridgeV1,
  CapabilityUiLocalizationProp,
} from './contracts';
import { CapabilityUiLocalizationProvider } from './provider';

function requireLocalization(
  localization: CapabilityUiLocalizationBridgeV1 | null | undefined,
): CapabilityUiLocalizationBridgeV1 {
  if (!localization) {
    throw new Error('Capability UI localization bridge is unavailable');
  }
  return localization;
}

export function createLocalizedCapabilityEntry<Props extends object>(
  DomainComponent: React.ComponentType<Props>,
): React.ComponentType<Props & CapabilityUiLocalizationProp> {
  function LocalizedCapabilityEntry({
    localization,
    ...props
  }: Props & CapabilityUiLocalizationProp) {
    return (
      <CapabilityUiLocalizationProvider
        localization={requireLocalization(localization)}
      >
        <DomainComponent {...props as Props} />
      </CapabilityUiLocalizationProvider>
    );
  }

  LocalizedCapabilityEntry.displayName =
    `LocalizedCapabilityEntry(${DomainComponent.displayName || DomainComponent.name || 'Component'})`;
  return LocalizedCapabilityEntry;
}

import type { ComponentType } from 'react';

import {
  loadCapabilityUiLocalization,
  type CapabilityUiLocalizationBridgeV1,
} from './capability-ui-localization';
import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from './capability-ui-loader';
import { getCapabilityUiMetadata } from './capability-ui-metadata-loader';
import type { Locale } from './i18n';

export interface LocalizedCapabilityUiComponent {
  Component: ComponentType<any>;
  localization: CapabilityUiLocalizationBridgeV1;
}

export async function loadLocalizedCapabilityUiComponent(options: {
  apiUrl: string;
  capabilityCode: string;
  componentCode: string;
  requestedLocale: Locale;
  workspaceId: string;
}): Promise<LocalizedCapabilityUiComponent | null> {
  const {
    apiUrl,
    capabilityCode,
    componentCode,
    requestedLocale,
    workspaceId,
  } = options;
  const metadata = await getCapabilityUiMetadata(apiUrl, capabilityCode, workspaceId);
  primeCapabilityUIComponentMetadata(capabilityCode, metadata.uiComponents);

  const [Component, localization] = await Promise.all([
    loadCapabilityUIComponent(
      capabilityCode,
      componentCode,
      apiUrl,
      workspaceId,
    ),
    loadCapabilityUiLocalization({
      apiUrl,
      workspaceId,
      capabilityCode,
      version: metadata.capabilityInfo.version || 'unversioned',
      requestedLocale,
      descriptor: metadata.capabilityInfo.ui_localization,
    }),
  ]);
  if (!Component) {
    return null;
  }
  return {
    Component,
    localization,
  };
}

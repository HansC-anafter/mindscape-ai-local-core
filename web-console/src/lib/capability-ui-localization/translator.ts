import IntlMessageFormat from 'intl-messageformat';

import type {
  CapabilityUiLocalizationBridgeV1,
  CapabilityUiLocalizationStatus,
  CapabilityUiTranslationValues,
  CompiledCapabilityUiCatalog,
} from './contracts';
import { CAPABILITY_UI_LOCALIZATION_BRIDGE_CONTRACT } from './contracts';
import type { Locale } from '@/lib/i18n';

export function createLegacyCapabilityUiLocalizationBridge(
  requestedLocale: Locale,
): CapabilityUiLocalizationBridgeV1 {
  return {
    contract: CAPABILITY_UI_LOCALIZATION_BRIDGE_CONTRACT,
    requestedLocale,
    effectiveLocale: requestedLocale,
    direction: 'ltr',
    sourceLocale: 'en',
    status: 'legacy-unmanaged',
    t: (key) => key,
  };
}

export function createCapabilityUiLocalizationBridge(
  catalog: CompiledCapabilityUiCatalog,
  requestedLocale: Locale,
  effectiveLocale: Locale,
  status: CapabilityUiLocalizationStatus,
): CapabilityUiLocalizationBridgeV1 {
  const compiledMessages = new Map<string, IntlMessageFormat>();

  return {
    contract: CAPABILITY_UI_LOCALIZATION_BRIDGE_CONTRACT,
    requestedLocale,
    effectiveLocale,
    direction: 'ltr',
    sourceLocale: 'en',
    status,
    t: (key: string, params?: CapabilityUiTranslationValues): string => {
      const message = catalog.messages[key];
      if (!message) {
        throw new Error(`Capability UI localization key is missing: ${key}`);
      }
      let compiled = compiledMessages.get(key);
      if (!compiled) {
        compiled = new IntlMessageFormat(message as never, effectiveLocale);
        compiledMessages.set(key, compiled);
      }
      const output = compiled.format(params as Record<string, never> | undefined);
      return Array.isArray(output)
        ? output.map((part) => String(part)).join('')
        : String(output);
    },
  };
}

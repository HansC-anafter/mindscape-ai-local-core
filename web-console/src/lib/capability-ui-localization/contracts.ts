import type { Locale } from '@/lib/i18n';

export const CAPABILITY_UI_LOCALIZATION_CONTRACT =
  'mindscape-capability-ui-localization-v1';
export const CAPABILITY_UI_LOCALIZATION_BRIDGE_CONTRACT =
  'mindscape-capability-ui-localization-bridge-v1';
export const CAPABILITY_UI_COMPILED_FORMAT =
  'formatjs-icu-messageformat-ast-v1';
export const CAPABILITY_UI_COMPILER =
  '@formatjs/icu-messageformat-parser@3.5.15';
export const CAPABILITY_UI_SOURCE_LOCALE: Locale = 'en';
export const CAPABILITY_UI_CATALOG_MAX_BYTES = 128 * 1024;

export type CapabilityUiLocalizationStatus =
  | 'localized'
  | 'source-fallback'
  | 'legacy-unmanaged';

export type CapabilityUiTranslationValues = Record<
  string,
  string | number | Date
>;

export interface CapabilityUiRuntimeCatalogDescriptor {
  asset_url: string;
  integrity: string;
  bytes: number;
}

export interface CapabilityUiRuntimeLocalizationDescriptor {
  contract: typeof CAPABILITY_UI_LOCALIZATION_CONTRACT;
  namespace: string;
  source_locale: 'en';
  fallback_locale: 'en';
  format: typeof CAPABILITY_UI_COMPILED_FORMAT;
  compiler: typeof CAPABILITY_UI_COMPILER;
  supported_locales: ['en', 'zh-TW', 'ja'];
  keyset_sha256: string;
  catalogs: Record<Locale, CapabilityUiRuntimeCatalogDescriptor>;
}

export interface CapabilityUiLocalizationBridgeV1 {
  contract: typeof CAPABILITY_UI_LOCALIZATION_BRIDGE_CONTRACT;
  requestedLocale: Locale;
  effectiveLocale: Locale;
  direction: 'ltr';
  sourceLocale: 'en';
  status: CapabilityUiLocalizationStatus;
  t: (
    key: string,
    params?: CapabilityUiTranslationValues,
  ) => string;
}

export interface CompiledCapabilityUiCatalog {
  format: typeof CAPABILITY_UI_COMPILED_FORMAT;
  compiler: typeof CAPABILITY_UI_COMPILER;
  namespace: string;
  locale: Locale;
  keyset_sha256: string;
  messages: Record<string, unknown[]>;
}

export interface LoadedCapabilityUiCatalog {
  catalog: CompiledCapabilityUiCatalog;
  bytes: number;
}

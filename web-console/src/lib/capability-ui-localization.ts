export {
  capabilityUiCatalogCacheStateForTests,
  clearCapabilityUiCatalogCacheForTests,
} from './capability-ui-localization/cache';
export {
  CAPABILITY_UI_CATALOG_MAX_BYTES,
  CAPABILITY_UI_COMPILED_FORMAT,
  CAPABILITY_UI_COMPILER,
  CAPABILITY_UI_LOCALIZATION_BRIDGE_CONTRACT,
  CAPABILITY_UI_LOCALIZATION_CONTRACT,
  type CapabilityUiLocalizationBridgeV1,
  type CapabilityUiLocalizationProp,
  type CapabilityUiRuntimeCatalogDescriptor,
  type CapabilityUiRuntimeLocalizationDescriptor,
  type CapabilityUiTranslationValues,
} from './capability-ui-localization/contracts';
export { createLocalizedCapabilityEntry } from './capability-ui-localization/entry';
export { loadCapabilityUiLocalization } from './capability-ui-localization/loader';
export {
  CapabilityMessage,
  CapabilityUiLocalizationProvider,
  useCapabilityLocalization,
  useOptionalCapabilityLocalization,
  useCapabilityT,
} from './capability-ui-localization/provider';

import { buildRuntimeAssetFetchUrl } from '@/lib/capability-runtime-asset-url';
import type { Locale } from '@/lib/i18n';

import { loadCachedCapabilityUiCatalog } from './cache';
import {
  CAPABILITY_UI_CATALOG_MAX_BYTES,
  CAPABILITY_UI_COMPILED_FORMAT,
  CAPABILITY_UI_COMPILER,
  CAPABILITY_UI_LOCALIZATION_CONTRACT,
  type CapabilityUiLocalizationBridgeV1,
  type CapabilityUiRuntimeCatalogDescriptor,
  type CapabilityUiRuntimeLocalizationDescriptor,
  type CompiledCapabilityUiCatalog,
  type LoadedCapabilityUiCatalog,
} from './contracts';
import {
  createCapabilityUiLocalizationBridge,
  createLegacyCapabilityUiLocalizationBridge,
} from './translator';

const CATALOG_TIMEOUT_MS = 2000;
const SUPPORTED_LOCALES: readonly Locale[] = ['en', 'zh-TW', 'ja'];

function catalogCacheKey(
  capabilityCode: string,
  version: string,
  locale: Locale,
  integrity: string,
): string {
  return [capabilityCode, version, locale, integrity].join('\u0000');
}

function absoluteAssetUrl(apiUrl: string, assetUrl: string): string {
  if (/^https?:\/\//.test(assetUrl)) return assetUrl;
  return `${apiUrl.replace(/\/$/, '')}/${assetUrl.replace(/^\//, '')}`;
}

async function sha256Integrity(bytes: Uint8Array): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    bytes as BufferSource,
  );
  const digestBytes = new Uint8Array(digest);
  let binary = '';
  for (const byte of digestBytes) binary += String.fromCharCode(byte);
  return `sha256-${globalThis.btoa(binary)}`;
}

async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    bytes as BufferSource,
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

async function readBoundedResponse(
  response: Response,
  controller: AbortController,
): Promise<Uint8Array> {
  const reader = response.body?.getReader();
  if (!reader) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > CAPABILITY_UI_CATALOG_MAX_BYTES) {
      throw new Error('Capability UI localization catalog exceeds 256 KiB');
    }
    return bytes;
  }

  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > CAPABILITY_UI_CATALOG_MAX_BYTES) {
      controller.abort();
      throw new Error('Capability UI localization catalog exceeds 256 KiB');
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

function assertAstElement(element: unknown, key: string): void {
  if (!element || typeof element !== 'object' || Array.isArray(element)) {
    throw new Error(`Capability UI localization AST is invalid for ${key}`);
  }
  const node = element as {
    type?: unknown;
    value?: unknown;
    options?: unknown;
  };
  if (!Number.isInteger(node.type) || Number(node.type) < 0 || Number(node.type) > 7) {
    throw new Error(`Capability UI localization AST type is invalid for ${key}`);
  }
  if (node.type === 5 || node.type === 6) {
    if (!node.options || typeof node.options !== 'object' || Array.isArray(node.options)) {
      throw new Error(`Capability UI localization AST options are invalid for ${key}`);
    }
    const options = node.options as Record<string, { value?: unknown }>;
    if (!options.other) {
      throw new Error(`Capability UI localization AST requires other for ${key}`);
    }
    for (const option of Object.values(options)) {
      if (!Array.isArray(option?.value)) {
        throw new Error(`Capability UI localization AST option is invalid for ${key}`);
      }
      for (const child of option.value) assertAstElement(child, key);
    }
  }
}

async function validateCompiledCatalog(
  bytes: Uint8Array,
  descriptor: CapabilityUiRuntimeLocalizationDescriptor,
  locale: Locale,
): Promise<CompiledCapabilityUiCatalog> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error('Capability UI localization catalog is invalid JSON');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Capability UI localization catalog must be an object');
  }
  const catalog = parsed as CompiledCapabilityUiCatalog;
  if (
    catalog.format !== CAPABILITY_UI_COMPILED_FORMAT
    || catalog.compiler !== CAPABILITY_UI_COMPILER
    || catalog.namespace !== descriptor.namespace
    || catalog.locale !== locale
    || catalog.keyset_sha256 !== descriptor.keyset_sha256
    || !catalog.messages
    || typeof catalog.messages !== 'object'
    || Array.isArray(catalog.messages)
  ) {
    throw new Error('Capability UI localization catalog metadata is invalid');
  }

  const keys = Object.keys(catalog.messages).sort();
  const computedKeyset = `sha256:${await sha256Hex(keys.join('\n'))}`;
  if (computedKeyset !== descriptor.keyset_sha256) {
    throw new Error('Capability UI localization keyset hash does not match');
  }
  for (const key of keys) {
    const message = catalog.messages[key];
    if (!key || !Array.isArray(message)) {
      throw new Error('Capability UI localization messages must be AST arrays');
    }
    for (const element of message) assertAstElement(element, key);
  }
  return catalog;
}

async function fetchCatalog(
  apiUrl: string,
  workspaceId: string,
  descriptor: CapabilityUiRuntimeLocalizationDescriptor,
  locale: Locale,
  catalogDescriptor: CapabilityUiRuntimeCatalogDescriptor,
): Promise<LoadedCapabilityUiCatalog> {
  if (
    !Number.isInteger(catalogDescriptor.bytes)
    || catalogDescriptor.bytes <= 0
    || catalogDescriptor.bytes > CAPABILITY_UI_CATALOG_MAX_BYTES
  ) {
    throw new Error('Capability UI localization descriptor byte budget is invalid');
  }
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(
    () => controller.abort(),
    CATALOG_TIMEOUT_MS,
  );
  try {
    const response = await fetch(
      buildRuntimeAssetFetchUrl(
        absoluteAssetUrl(apiUrl, catalogDescriptor.asset_url),
        undefined,
        workspaceId,
      ),
      {
        credentials: 'same-origin',
        cache: 'force-cache',
        signal: controller.signal,
      },
    );
    if (!response.ok) {
      throw new Error(
        `Capability UI localization request failed: ${response.status}`,
      );
    }
    const bytes = await readBoundedResponse(response, controller);
    if (bytes.byteLength !== catalogDescriptor.bytes) {
      throw new Error('Capability UI localization byte count does not match');
    }
    if (await sha256Integrity(bytes) !== catalogDescriptor.integrity) {
      throw new Error('Capability UI localization integrity does not match');
    }
    return {
      catalog: await validateCompiledCatalog(bytes, descriptor, locale),
      bytes: bytes.byteLength,
    };
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

function validateDescriptor(
  capabilityCode: string,
  descriptor: CapabilityUiRuntimeLocalizationDescriptor,
): void {
  if (
    descriptor.contract !== CAPABILITY_UI_LOCALIZATION_CONTRACT
    || descriptor.namespace !== capabilityCode
    || descriptor.source_locale !== 'en'
    || descriptor.fallback_locale !== 'en'
    || descriptor.format !== CAPABILITY_UI_COMPILED_FORMAT
    || descriptor.compiler !== CAPABILITY_UI_COMPILER
    || JSON.stringify(descriptor.supported_locales) !== JSON.stringify(SUPPORTED_LOCALES)
    || !descriptor.catalogs
  ) {
    throw new Error('Capability UI localization descriptor is invalid');
  }
}

async function loadLocaleCatalog(
  apiUrl: string,
  workspaceId: string,
  capabilityCode: string,
  version: string,
  descriptor: CapabilityUiRuntimeLocalizationDescriptor,
  locale: Locale,
): Promise<LoadedCapabilityUiCatalog> {
  const catalogDescriptor = descriptor.catalogs[locale];
  if (!catalogDescriptor) {
    throw new Error(`Capability UI localization descriptor has no ${locale} catalog`);
  }
  return loadCachedCapabilityUiCatalog(
    catalogCacheKey(
      capabilityCode,
      version,
      locale,
      catalogDescriptor.integrity,
    ),
    () => fetchCatalog(
      apiUrl,
      workspaceId,
      descriptor,
      locale,
      catalogDescriptor,
    ),
  );
}

export async function loadCapabilityUiLocalization(options: {
  apiUrl: string;
  workspaceId: string;
  capabilityCode: string;
  version: string;
  requestedLocale: Locale;
  descriptor?: CapabilityUiRuntimeLocalizationDescriptor;
}): Promise<CapabilityUiLocalizationBridgeV1> {
  const {
    apiUrl,
    workspaceId,
    capabilityCode,
    version,
    requestedLocale,
    descriptor,
  } = options;
  if (!descriptor) {
    return createLegacyCapabilityUiLocalizationBridge(requestedLocale);
  }
  const normalizedWorkspaceId = workspaceId.trim();
  if (!normalizedWorkspaceId) {
    throw new Error('Capability UI localization workspace is required');
  }
  validateDescriptor(capabilityCode, descriptor);

  try {
    const loaded = await loadLocaleCatalog(
      apiUrl,
      normalizedWorkspaceId,
      capabilityCode,
      version,
      descriptor,
      requestedLocale,
    );
    return createCapabilityUiLocalizationBridge(
      loaded.catalog,
      requestedLocale,
      requestedLocale,
      'localized',
    );
  } catch (requestedError) {
    if (requestedLocale === 'en') throw requestedError;
    const source = await loadLocaleCatalog(
      apiUrl,
      normalizedWorkspaceId,
      capabilityCode,
      version,
      descriptor,
      'en',
    );
    return createCapabilityUiLocalizationBridge(
      source.catalog,
      requestedLocale,
      'en',
      'source-fallback',
    );
  }
}

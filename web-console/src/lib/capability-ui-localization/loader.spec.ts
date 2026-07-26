import { createHash } from 'node:crypto';

import { parse } from '@formatjs/icu-messageformat-parser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  capabilityUiCatalogCacheStateForTests,
  clearCapabilityUiCatalogCacheForTests,
  loadCapabilityUiLocalization,
  type CapabilityUiRuntimeLocalizationDescriptor,
} from '@/lib/capability-ui-localization';

const encoder = new TextEncoder();

function sha256Hex(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

function integrity(bytes: Uint8Array): string {
  return `sha256-${createHash('sha256').update(bytes).digest('base64')}`;
}

function catalogBytes(
  namespace: string,
  locale: 'en' | 'zh-TW' | 'ja',
  keyset: string,
  message: string,
): Uint8Array {
  return encoder.encode(`${JSON.stringify({
    format: 'formatjs-icu-messageformat-ast-v1',
    compiler: '@formatjs/icu-messageformat-parser@3.5.15',
    namespace,
    locale,
    keyset_sha256: keyset,
    messages: {
      greeting: parse(message),
    },
  })}\n`);
}

function fixture(namespace = 'demo_pack'): {
  descriptor: CapabilityUiRuntimeLocalizationDescriptor;
  assets: Record<string, Uint8Array>;
} {
  const keyset = `sha256:${sha256Hex('greeting')}`;
  const assets = {
    en: catalogBytes(namespace, 'en', keyset, 'Hello, {name}'),
    'zh-TW': catalogBytes(namespace, 'zh-TW', keyset, '你好，{name}'),
    ja: catalogBytes(namespace, 'ja', keyset, 'こんにちは、{name}'),
  };
  const descriptor: CapabilityUiRuntimeLocalizationDescriptor = {
    contract: 'mindscape-capability-ui-localization-v1',
    namespace,
    source_locale: 'en',
    fallback_locale: 'en',
    format: 'formatjs-icu-messageformat-ast-v1',
    compiler: '@formatjs/icu-messageformat-parser@3.5.15',
    supported_locales: ['en', 'zh-TW', 'ja'],
    keyset_sha256: keyset,
    catalogs: {
      en: {
        asset_url: '/assets/en.json',
        integrity: integrity(assets.en),
        bytes: assets.en.byteLength,
      },
      'zh-TW': {
        asset_url: '/assets/zh-TW.json',
        integrity: integrity(assets['zh-TW']),
        bytes: assets['zh-TW'].byteLength,
      },
      ja: {
        asset_url: '/assets/ja.json',
        integrity: integrity(assets.ja),
        bytes: assets.ja.byteLength,
      },
    },
  };
  return { descriptor, assets };
}

function localeFromUrl(url: string): 'en' | 'zh-TW' | 'ja' {
  if (url.endsWith('/zh-TW.json')) return 'zh-TW';
  if (url.endsWith('/ja.json')) return 'ja';
  return 'en';
}

beforeEach(() => {
  clearCapabilityUiCatalogCacheForTests();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('capability UI localization loader', () => {
  it('singleflights one immutable requested-locale fetch', async () => {
    const { descriptor, assets } = fixture();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const locale = localeFromUrl(String(input));
      return new Response(assets[locale], { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const options = {
      apiUrl: 'http://api.test',
      capabilityCode: 'demo_pack',
      version: '1.0.0',
      requestedLocale: 'zh-TW' as const,
      descriptor,
    };
    const [first, second] = await Promise.all([
      loadCapabilityUiLocalization(options),
      loadCapabilityUiLocalization(options),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first.status).toBe('localized');
    expect(second.effectiveLocale).toBe('zh-TW');
    expect(first.t('greeting', { name: 'Ada' })).toBe('你好，Ada');
  });

  it('does no retry and fetches English once after a corrupt requested catalog', async () => {
    const { descriptor, assets } = fixture();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const locale = localeFromUrl(String(input));
      const bytes = locale === 'zh-TW'
        ? encoder.encode('corrupt')
        : assets[locale];
      return new Response(bytes, { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const bridge = await loadCapabilityUiLocalization({
      apiUrl: 'http://api.test',
      capabilityCode: 'demo_pack',
      version: '1.0.0',
      requestedLocale: 'zh-TW',
      descriptor,
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(bridge.status).toBe('source-fallback');
    expect(bridge.effectiveLocale).toBe('en');
    expect(bridge.t('greeting', { name: 'Ada' })).toBe('Hello, Ada');
  });

  it('fails without mounting when the English source catalog is invalid', async () => {
    const { descriptor } = fixture();
    const fetchMock = vi.fn(async () => (
      new Response(encoder.encode('corrupt'), { status: 200 })
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadCapabilityUiLocalization({
      apiUrl: 'http://api.test',
      capabilityCode: 'demo_pack',
      version: '1.0.0',
      requestedLocale: 'en',
      descriptor,
    })).rejects.toThrow(/byte count|integrity|JSON/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('bounds the immutable cache at 32 entries', async () => {
    const { descriptor, assets } = fixture();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const locale = localeFromUrl(String(input));
      return new Response(assets[locale], { status: 200 });
    }));

    for (let index = 0; index < 33; index += 1) {
      await loadCapabilityUiLocalization({
        apiUrl: 'http://api.test',
        capabilityCode: 'demo_pack',
        version: `1.0.${index}`,
        requestedLocale: 'en',
        descriptor,
      });
    }
    const state = capabilityUiCatalogCacheStateForTests();
    expect(state.entries).toBe(32);
    expect(state.bytes).toBeLessThanOrEqual(4 * 1024 * 1024);
  });

  it('aborts one source request at two seconds without retry', async () => {
    vi.useFakeTimers();
    const { descriptor } = fixture();
    const fetchMock = vi.fn((
      _input: RequestInfo | URL,
      init?: RequestInit,
    ) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => {
        reject(new DOMException('aborted', 'AbortError'));
      });
    }));
    vi.stubGlobal('fetch', fetchMock);

    const loading = loadCapabilityUiLocalization({
      apiUrl: 'http://api.test',
      capabilityCode: 'demo_pack',
      version: '1.0.0',
      requestedLocale: 'en',
      descriptor,
    });
    const rejection = expect(loading).rejects.toMatchObject({
      name: 'AbortError',
    });
    await vi.advanceTimersByTimeAsync(2000);

    await rejection;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('produces a deterministic legacy bridge without a network request', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const bridge = await loadCapabilityUiLocalization({
      apiUrl: 'http://api.test',
      capabilityCode: 'legacy_pack',
      version: '1.0.0',
      requestedLocale: 'ja',
    });

    expect(bridge.status).toBe('legacy-unmanaged');
    expect(bridge.requestedLocale).toBe('ja');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

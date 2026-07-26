import 'server-only';

import { cache } from 'react';
import { headers } from 'next/headers';

import { getServiceEndpointUrl } from '../../../../packages/core/src/api';

import {
  isLocale,
  type LocaleSnapshot,
  type Translator,
} from './contracts';
import { createTranslator } from './translator';

const HARD_DEFAULT_SNAPSHOT: Omit<LocaleSnapshot, 'writable'> = {
  locale: 'zh-TW',
  version: null,
  source: 'degraded',
};
const PROFILE_UI_LANGUAGE_PATH =
  '/api/v1/mindscape/profiles/me/preferences/ui-language';
const BOOTSTRAP_TIMEOUT_MS = 1_000;

function executionApiOrigin(): string {
  return (
    process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL
    || process.env.WEB_CONSOLE_BACKEND_EXECUTION_URL
    || process.env.HOST_RUNTIME_BACKEND_URL
    || getServiceEndpointUrl('local_core.execution_api', 'container_internal')
    || ''
  ).replace(/\/+$/, '');
}

function validProjection(
  value: unknown,
): value is { locale: LocaleSnapshot['locale']; version: number; source: 'profile' | 'system_seed' | 'hard_default' } {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as {
    locale?: unknown;
    version?: unknown;
    source?: unknown;
  };
  return (
    isLocale(candidate.locale)
    && Number.isInteger(candidate.version)
    && Number(candidate.version) >= 1
    && (
      candidate.source === 'profile'
      || candidate.source === 'system_seed'
      || candidate.source === 'hard_default'
    )
  );
}

export const getServerLocaleSnapshot = cache(
  async (): Promise<LocaleSnapshot> => {
    const requestHeaders = headers();
    const remoteDocument =
      requestHeaders.get('x-mindscape-remote-ingress') === 'remote_workbench';
    const fallback = {
      ...HARD_DEFAULT_SNAPSHOT,
      writable: !remoteDocument,
    };
    const origin = executionApiOrigin();
    if (!origin) return fallback;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), BOOTSTRAP_TIMEOUT_MS);
    try {
      const authorization = requestHeaders.get('authorization');
      const response = await fetch(`${origin}${PROFILE_UI_LANGUAGE_PATH}`, {
        method: 'GET',
        headers:
          authorization?.startsWith('Bearer ')
            ? { Authorization: authorization }
            : undefined,
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) return fallback;

      const projection: unknown = await response.json();
      if (!validProjection(projection)) return fallback;
      return {
        ...projection,
        writable: !remoteDocument,
      };
    } catch {
      return fallback;
    } finally {
      clearTimeout(timeout);
    }
  },
);

export async function getServerT(): Promise<Translator> {
  const snapshot = await getServerLocaleSnapshot();
  return createTranslator(snapshot.locale);
}

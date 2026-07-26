'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useRouter } from 'next/navigation';

import { getApiBaseUrl } from '../api-url';
import {
  LOCALE_DIRECTION,
  isLocale,
  type Locale,
  type LocaleSnapshot,
  type Translator,
} from './contracts';
import { createTranslator } from './translator';

const PROFILE_PREFERENCES_PATH =
  '/api/v1/mindscape/profiles/me/preferences';
const PATCH_TIMEOUT_MS = 2_000;

interface LocaleContextValue extends LocaleSnapshot {
  saving: boolean;
  error: string | null;
  setLocale: (locale: Locale) => Promise<void>;
  t: Translator;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

function projectionFromResponse(value: unknown): Pick<LocaleSnapshot, 'locale' | 'version' | 'source'> | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as {
    locale?: unknown;
    version?: unknown;
    source?: unknown;
  };
  if (
    !isLocale(candidate.locale)
    || !Number.isInteger(candidate.version)
    || Number(candidate.version) < 1
    || (
      candidate.source !== 'profile'
      && candidate.source !== 'system_seed'
      && candidate.source !== 'hard_default'
    )
  ) {
    return null;
  }
  return {
    locale: candidate.locale,
    version: Number(candidate.version),
    source: candidate.source,
  };
}

export function LocaleProvider({
  initialSnapshot,
  children,
}: {
  initialSnapshot: LocaleSnapshot;
  children: ReactNode;
}) {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.lang = snapshot.locale;
    document.documentElement.dir = LOCALE_DIRECTION[snapshot.locale];
  }, [snapshot.locale]);

  const setLocale = useCallback(async (locale: Locale) => {
    if (locale === snapshot.locale) return;
    if (!snapshot.writable) {
      const message = 'UI language is read-only on this remote surface.';
      setError(message);
      throw new Error(message);
    }
    if (snapshot.version === null) {
      const message =
        'UI language cannot be saved until the profile is available.';
      setError(message);
      throw new Error(message);
    }

    setSaving(true);
    setError(null);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), PATCH_TIMEOUT_MS);
    try {
      const response = await fetch(
        `${getApiBaseUrl()}${PROFILE_PREFERENCES_PATH}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            preferred_ui_language: locale,
            expected_version: snapshot.version,
          }),
          cache: 'no-store',
          signal: controller.signal,
        },
      );
      if (response.status === 409) {
        throw new Error(
          'UI language changed elsewhere. Refresh before submitting again.',
        );
      }
      if (!response.ok) {
        throw new Error(`UI language update failed (${response.status}).`);
      }
      const projection = projectionFromResponse(await response.json());
      if (!projection) {
        throw new Error('UI language update returned an invalid projection.');
      }
      setSnapshot((current) => ({
        ...current,
        ...projection,
      }));
      router.refresh();
    } catch (caught) {
      const message =
        caught instanceof Error
          ? caught.message
          : 'UI language update failed.';
      setError(message);
      throw caught;
    } finally {
      clearTimeout(timeout);
      setSaving(false);
    }
  }, [router, snapshot.locale, snapshot.version, snapshot.writable]);

  const value = useMemo<LocaleContextValue>(() => ({
    ...snapshot,
    saving,
    error,
    setLocale,
    t: createTranslator(snapshot.locale),
  }), [error, saving, setLocale, snapshot]);

  return (
    <LocaleContext.Provider value={value}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocaleContext(): LocaleContextValue {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error('useLocaleContext must be used within LocaleProvider');
  }
  return context;
}

export function useLocale(): [Locale, (locale: Locale) => Promise<void>] {
  const { locale, setLocale } = useLocaleContext();
  return [locale, setLocale];
}

export function useT(): Translator {
  return useLocaleContext().t;
}

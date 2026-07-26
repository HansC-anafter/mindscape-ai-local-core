import type { MessageKey } from './keys';

export const SUPPORTED_LOCALES = ['zh-TW', 'en', 'ja'] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const LOCALE_DIRECTION: Record<Locale, 'ltr' | 'rtl'> = {
  'zh-TW': 'ltr',
  en: 'ltr',
  ja: 'ltr',
};

export type LocaleSnapshotSource =
  | 'profile'
  | 'system_seed'
  | 'hard_default'
  | 'degraded';

export interface LocaleSnapshot {
  locale: Locale;
  version: number | null;
  source: LocaleSnapshotSource;
  writable: boolean;
}

export type TranslationValues = Record<string, unknown>;
export type Translator = (
  key: MessageKey,
  values?: TranslationValues,
) => string;

export function isLocale(value: unknown): value is Locale {
  return (
    typeof value === 'string'
    && (SUPPORTED_LOCALES as readonly string[]).includes(value)
  );
}

export type { MessageKey };

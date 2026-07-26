import IntlMessageFormat from 'intl-messageformat';

import { hostCatalogs } from './catalogs';
import type {
  Locale,
  MessageKey,
  TranslationValues,
  Translator,
} from './contracts';

const SOURCE_LOCALE: Locale = 'en';
const compiledMessages = new Map<string, IntlMessageFormat>();

function messageFor(locale: Locale, key: MessageKey): string | undefined {
  const localeCatalog = hostCatalogs[locale] as Record<string, string>;
  const sourceCatalog = hostCatalogs[SOURCE_LOCALE] as Record<string, string>;
  return localeCatalog[key] ?? sourceCatalog[key];
}

function compiledMessage(
  locale: Locale,
  key: MessageKey,
  message: string,
): IntlMessageFormat {
  const cacheKey = `${locale}\u0000${key}`;
  const cached = compiledMessages.get(cacheKey);
  if (cached) return cached;

  const compiled = new IntlMessageFormat(message, locale);
  compiledMessages.set(cacheKey, compiled);
  return compiled;
}

export function translate(
  locale: Locale,
  key: MessageKey,
  values?: TranslationValues,
): string {
  const message = messageFor(locale, key);
  if (message === undefined) return key;
  if (values === undefined) return message;

  const output = compiledMessage(locale, key, message).format(
    values as Record<string, never> | undefined,
  );
  return Array.isArray(output)
    ? output.map((part) => String(part)).join('')
    : String(output);
}

export function formatIcuMessage(
  message: string,
  locale: Locale,
  values?: TranslationValues,
): string {
  const output = new IntlMessageFormat(message, locale).format(
    values as Record<string, never> | undefined,
  );
  return Array.isArray(output)
    ? output.map((part) => String(part)).join('')
    : String(output);
}

export function createTranslator(locale: Locale): Translator {
  return (key, values) => translate(locale, key, values);
}

export function clearHostMessageCacheForTests(): void {
  compiledMessages.clear();
}

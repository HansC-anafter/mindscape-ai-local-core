import { parse, TYPE, type MessageFormatElement } from '@formatjs/icu-messageformat-parser';
import { describe, expect, it } from 'vitest';

import { hostCatalogs } from './catalogs';
import { SUPPORTED_LOCALES, type Locale } from './contracts';
import { formatIcuMessage } from './translator';

type ArgumentShape = Map<string, string>;

function argumentShape(message: string): ArgumentShape {
  const shape: ArgumentShape = new Map();
  const visit = (elements: MessageFormatElement[]) => {
    for (const element of elements) {
      if (
        element.type === TYPE.argument
        || element.type === TYPE.number
        || element.type === TYPE.date
        || element.type === TYPE.time
        || element.type === TYPE.select
        || element.type === TYPE.plural
      ) {
        shape.set(element.value, TYPE[element.type]);
      }
      if (element.type === TYPE.select || element.type === TYPE.plural) {
        expect(element.options.other).toBeDefined();
        Object.values(element.options).forEach((option) => visit(option.value));
      }
      if (element.type === TYPE.tag) {
        throw new Error('Host v1 messages cannot contain rich-text tags');
      }
    }
  };
  visit(parse(message));
  return shape;
}

describe('host i18n catalogs', () => {
  it('keeps exact source-locale key parity', () => {
    const sourceKeys = Object.keys(hostCatalogs.en).sort();
    for (const locale of SUPPORTED_LOCALES) {
      expect(Object.keys(hostCatalogs[locale]).sort()).toEqual(sourceKeys);
    }
  });

  it('keeps ICU argument names and types aligned with English', () => {
    const source = hostCatalogs.en as Record<string, string>;
    const mismatches: string[] = [];
    for (const locale of SUPPORTED_LOCALES) {
      const catalog = hostCatalogs[locale] as Record<string, string>;
      for (const key of Object.keys(source)) {
        const localizedShape = JSON.stringify(
          [...argumentShape(catalog[key]).entries()].sort(),
        );
        const sourceShape = JSON.stringify(
          [...argumentShape(source[key]).entries()].sort(),
        );
        if (localizedShape !== sourceShape) {
          mismatches.push(`${locale}:${key}`);
        }
      }
    }
    expect(mismatches).toEqual([]);
  });

  it('formats plural, select, number, and date ICU syntax', () => {
    expect(formatIcuMessage(
      '{count, plural, one {# item} other {# items}}',
      'en',
      { count: 2 },
    )).toBe('2 items');
    expect(formatIcuMessage(
      '{mode, select, local {Local} other {Remote}} · {count, number}',
      'en',
      { mode: 'local', count: 1234 },
    )).toContain('Local');
    expect(formatIcuMessage(
      '{value, date, short}',
      'en',
      { value: new Date('2026-07-27T00:00:00Z') },
    )).not.toBe('');
  });
});

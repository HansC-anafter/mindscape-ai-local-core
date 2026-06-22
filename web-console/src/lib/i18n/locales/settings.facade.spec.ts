import { describe, expect, it } from 'vitest';

import { settingsEn as canonicalSettingsEn } from './en/settings';
import { settingsZhTW as canonicalSettingsZhTW } from './zh-TW/settings';
import { settingsEn as legacySettingsEn, settingsZhTW as legacySettingsZhTW } from './settings';

describe('settings legacy facade', () => {
  it('exports the canonical Traditional Chinese settings object', () => {
    expect(legacySettingsZhTW).toBe(canonicalSettingsZhTW);
  });

  it('exports the canonical English settings object', () => {
    expect(legacySettingsEn).toBe(canonicalSettingsEn);
  });
});

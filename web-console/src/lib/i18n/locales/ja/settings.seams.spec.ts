import { describe, expect, it } from 'vitest';

import { settingsJa } from './settings';
import { settingsJaCloudExtensionAndBackup } from './settingsSections/cloudExtensionAndBackup';

describe('Japanese settings locale seams', () => {
  it('exposes every cloud extension and backup message through settingsJa', () => {
    for (const [key, value] of Object.entries(settingsJaCloudExtensionAndBackup)) {
      expect(settingsJa[key as keyof typeof settingsJa]).toBe(value);
    }
  });

  it('keeps adjacent settings groups on the public locale object', () => {
    expect(settingsJa.settings).toBeDefined();
    expect(settingsJa.storagePathConfigured).toBeDefined();
  });
});

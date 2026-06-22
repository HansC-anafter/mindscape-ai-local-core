import { describe, expect, it } from 'vitest';

import { settingsEn } from './settings';
import { settingsEnCloudProviders } from './settingsSections/cloudProviders';
import { settingsEnRuntimeAndBackup } from './settingsSections/runtimeAndBackup';
import { settingsEnWorkspaceResources } from './settingsSections/workspaceResources';

const expectMessagesToBePublic = (messages: Partial<Record<keyof typeof settingsEn, string>>) => {
  for (const [key, value] of Object.entries(messages)) {
    expect(settingsEn[key as keyof typeof settingsEn]).toBe(value);
  }
};

describe('English settings locale seams', () => {
  it('exposes every workspace resource message through settingsEn', () => {
    expectMessagesToBePublic(settingsEnWorkspaceResources);
  });

  it('exposes every cloud provider message through settingsEn', () => {
    expectMessagesToBePublic(settingsEnCloudProviders);
  });

  it('exposes every runtime and backup message through settingsEn', () => {
    expectMessagesToBePublic(settingsEnRuntimeAndBackup);
  });

  it('keeps adjacent settings and SaaS groups on the public locale object', () => {
    expect(settingsEn.settings).toBe('Settings');
    expect(settingsEn.packProductDesignerName).toBe('Graphic Design Assistant Pack');
    expect(settingsEn.slackConnectionSuccess).toBe('Slack connected successfully');
  });
});

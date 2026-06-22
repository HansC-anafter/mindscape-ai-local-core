import { describe, expect, it } from 'vitest';

import { settingsZhTW } from './settings';
import { settingsZhTWCloudProviders } from './settingsSections/cloudProviders';
import { settingsZhTWRuntimeAndBackup } from './settingsSections/runtimeAndBackup';
import { settingsZhTWWorkspaceResources } from './settingsSections/workspaceResources';

const expectMessagesToBePublic = (messages: Partial<Record<keyof typeof settingsZhTW, string>>) => {
  for (const [key, value] of Object.entries(messages)) {
    expect(settingsZhTW[key as keyof typeof settingsZhTW]).toBe(value);
  }
};

describe('Traditional Chinese settings locale seams', () => {
  it('exposes every workspace resource message through settingsZhTW', () => {
    expectMessagesToBePublic(settingsZhTWWorkspaceResources);
  });

  it('exposes every cloud provider message through settingsZhTW', () => {
    expectMessagesToBePublic(settingsZhTWCloudProviders);
  });

  it('exposes every runtime and backup message through settingsZhTW', () => {
    expectMessagesToBePublic(settingsZhTWRuntimeAndBackup);
  });

  it('keeps adjacent settings and SaaS groups on the public locale object', () => {
    expect(settingsZhTW.settings).toBe('設定');
    expect(settingsZhTW.packProductDesignerName).toBe('平面設計助理 Pack');
    expect(settingsZhTW.slackConnectionSuccess).toBe('Slack 連接成功');
  });
});

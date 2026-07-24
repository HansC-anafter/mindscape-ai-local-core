import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  mobileNavigationItems,
  navigationItems,
  validSettingsTabs,
} from './settingsNavigationRegistry';

describe('settings navigation registry', () => {
  it('exposes Remote Workbench Access as one top-level settings owner', () => {
    const matches = navigationItems.filter((item) => item.tab === 'remote_workbench_access');

    expect(matches).toHaveLength(1);
    expect(matches[0]).toMatchObject({
      id: 'remote-workbench-access',
      label: 'remoteWorkbenchAccess',
      tab: 'remote_workbench_access',
    });
    expect(matches[0].children).toBeUndefined();
  });

  it('derives valid tabs and preserves the existing mobile visibility and order', () => {
    expect(validSettingsTabs).toEqual(navigationItems.map((item) => item.tab));
    expect(mobileNavigationItems.map((item) => item.tab)).toEqual([
      'basic',
      'credentials',
      'mindscape',
      'social_media',
      'localization',
      'workspace_products',
      'packs_status',
      'governance',
      'runtime',
      'remote_workbench_access',
      'service_status',
    ]);
    expect(mobileNavigationItems.some((item) => item.tab === 'tools')).toBe(false);
    expect(mobileNavigationItems.some((item) => item.tab === 'ai-team-governance')).toBe(false);
  });

  it('keeps content hosting as a complete component switch without a second metadata source', () => {
    const webConsoleRoot = path.basename(process.cwd()) === 'web-console'
      ? process.cwd()
      : path.resolve(process.cwd(), 'web-console');
    const contentHostSource = readFileSync(
      path.resolve(webConsoleRoot, 'src/app/settings/components/SettingsContentHost.tsx'),
      'utf8',
    );

    validSettingsTabs.forEach((tab) => {
      expect(contentHostSource).toContain(`case '${tab}':`);
    });
    expect(contentHostSource).not.toMatch(/navigationItems|mobileNavigationItems|validSettingsTabs|fetch\(/);
  });
});

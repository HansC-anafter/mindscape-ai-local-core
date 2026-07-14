import { describe, expect, it } from 'vitest';

import { navigationItems } from './settingsNavigationRegistry';

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
});

import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockRedirect = vi.fn();

vi.mock('next/navigation', () => ({
  redirect: (...args: any[]) => mockRedirect(...args),
}));

import LegacyCapabilityUiHostRedirectPage from './[capabilityCode]/[workspaceId]/[[...surfacePath]]/page';

describe('legacy capability UI host redirect', () => {
  beforeEach(() => {
    mockRedirect.mockReset();
  });

  it('redirects every top-level host shape to the canonical workspace route', () => {
    LegacyCapabilityUiHostRedirectPage({
      params: {
        capabilityCode: 'ig',
        workspaceId: 'ws_demo',
        surfacePath: ['spaces', 'sp_001'],
      },
      searchParams: {
        component: 'IGWorkbenchPage',
        tag: ['reference', 'brief'],
      },
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/workspaces/ws_demo/capability-ui-hosts/ig/spaces/sp_001?component=IGWorkbenchPage&tag=reference&tag=brief',
    );
  });
});

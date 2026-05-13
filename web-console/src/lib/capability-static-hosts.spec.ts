import { describe, expect, it } from 'vitest';
import { buildCapabilityWorkbenchPath } from './capability-static-hosts';

describe('capability workbench routing', () => {
  it('builds canonical workspace-scoped host paths for every capability code', () => {
    expect(
      buildCapabilityWorkbenchPath('ws one', 'brand_identity', {
        searchParams: {
          component: 'StoryboardPage',
          tag: ['a', 'b'],
        },
      }),
    ).toBe('/workspaces/ws%20one/capability-ui-hosts/brand_identity?component=StoryboardPage&tag=a&tag=b');

    expect(
      buildCapabilityWorkbenchPath('ws one', 'ig', {
        searchParams: { component: 'IGWorkbench' },
      }),
    ).toBe('/workspaces/ws%20one/capability-ui-hosts/ig?component=IGWorkbench');

    expect(
      buildCapabilityWorkbenchPath('ws one', 'performance_direction', {
        searchParams: { session_id: 'ds_1' },
      }),
    ).toBe('/workspaces/ws%20one/capability-ui-hosts/performance_direction?session_id=ds_1');
  });

  it('preserves opaque surface path segments under the canonical host', () => {
    expect(
      buildCapabilityWorkbenchPath('ws one', 'performance_direction', {
        surfacePath: ['sessions', 'ds route 001'],
      }),
    ).toBe('/workspaces/ws%20one/capability-ui-hosts/performance_direction/sessions/ds%20route%20001');
  });

  it('rejects pre-joined or empty route segments', () => {
    expect(() =>
      buildCapabilityWorkbenchPath('ws_one', 'performance_direction', {
        surfacePath: ['sessions/ds_1'],
      }),
    ).toThrow('surfacePath[0] must not contain "/"');
    expect(() => buildCapabilityWorkbenchPath('ws/one', 'ig')).toThrow(
      'workspaceId must not contain "/"',
    );
    expect(() => buildCapabilityWorkbenchPath('', 'ig')).toThrow('workspaceId must be a non-empty raw segment');
  });
});

import { describe, expect, it } from 'vitest';
import {
  buildStaticCapabilityHostPath,
  resolveStaticCapabilityHostCode,
} from './capability-static-hosts';

describe('capability static host routing', () => {
  it('resolves known host codes and code variants', () => {
    expect(resolveStaticCapabilityHostCode('ig')).toBe('ig');
    expect(resolveStaticCapabilityHostCode('brand-identity')).toBe('brand_identity');
    expect(resolveStaticCapabilityHostCode('performance-direction')).toBeNull();
    expect(resolveStaticCapabilityHostCode('unknown_pack')).toBeNull();
  });

  it('builds static host paths without dropping query parameters', () => {
    expect(
      buildStaticCapabilityHostPath('ws/one', 'brand_identity', {
        component: 'StoryboardPage',
        tag: ['a', 'b'],
      }),
    ).toBe('/workspaces/ws%2Fone/capability-ui-hosts/brand_identity?component=StoryboardPage&tag=a&tag=b');
  });
});

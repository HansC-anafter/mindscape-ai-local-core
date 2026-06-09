import { describe, expect, it } from 'vitest';

import { isMainPageComponent, type UIComponentInfo } from './CapabilityLoadedComponentsView';

function component(code: string): UIComponentInfo {
  return {
    code,
    path: `ui/components/${code}.tsx`,
    description: code,
    export: 'default',
    artifact_types: [],
    playbook_codes: [],
    import_path: `@/app/capabilities/example/components/${code}`,
  };
}

describe('CapabilityLoadedComponentsView', () => {
  it('treats workbench components as full-page capability entry points', () => {
    expect(isMainPageComponent(component('CreativeStudioWorkbench'))).toBe(true);
    expect(isMainPageComponent(component('CreativeStudioSeedSproutPlane'))).toBe(false);
    expect(isMainPageComponent(component('ReferenceGridCard'))).toBe(false);
  });
});

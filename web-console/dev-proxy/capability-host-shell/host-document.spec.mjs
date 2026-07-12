import { describe, expect, it } from 'vitest';

import { renderCapabilityHostDocument } from './host-document.mjs';

describe('capability host shell document', () => {
  it('renders a themed host document that delegates runtime behavior to static assets', () => {
    const body = renderCapabilityHostDocument({
      workspaceId: 'ws<one',
      capabilityCode: 'ig',
      surfacePath: ['assets'],
    });

    expect(body).toContain('<html lang="en" class="theme-warm">');
    for (const asset of [
      'app-layout.css',
      'react.production.min.js',
      'react-dom.production.min.js',
      'shell-runtime.browser.js',
    ]) {
      expect(body).toContain(
        `__mindscape-capability-host/${asset}?workspace_id=ws%3Cone&capability_code=ig`,
      );
    }
    expect(body).toContain('mindscape-capability-host-config');
    expect(body).toContain('"workspaceId":"ws\\u003cone"');
    expect(body).not.toContain('MindscapeRuntimeReact');
    expect(body).not.toContain('fetchJson');
  });
});

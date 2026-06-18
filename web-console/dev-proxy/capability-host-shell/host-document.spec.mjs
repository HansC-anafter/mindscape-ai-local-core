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
    expect(body).toContain('__mindscape-capability-host/app-layout.css');
    expect(body).toContain('__mindscape-capability-host/react.production.min.js');
    expect(body).toContain('__mindscape-capability-host/react-dom.production.min.js');
    expect(body).toContain('__mindscape-capability-host/shell-runtime.browser.js');
    expect(body).toContain('mindscape-capability-host-config');
    expect(body).toContain('"workspaceId":"ws\\u003cone"');
    expect(body).not.toContain('MindscapeRuntimeReact');
    expect(body).not.toContain('fetchJson');
  });
});

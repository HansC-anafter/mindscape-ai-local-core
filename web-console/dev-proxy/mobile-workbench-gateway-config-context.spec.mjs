import assert from 'node:assert/strict';
import test from 'node:test';

import * as gateway from './mobile-workbench-gateway.mjs';

test('gateway remains disabled without an explicit operational enable flag', () => {
  const config = gateway.resolveMobileWorkbenchGatewayConfig({});
  assert.equal(config.enabled, false);
  assert.equal(config.remoteListenerReady, false);
  assert.equal(config.reason, 'disabled');
});

test('no synchronous authorization or Host-loopback bypass export remains', () => {
  assert.equal('isMobileWorkbenchGatewayRequestAllowed' in gateway, false);
  assert.equal('isLoopbackControlPlaneRequest' in gateway, false);
  assert.equal(typeof gateway.authorizeRemoteWorkbenchRequest, 'function');
});

test('request context uses route/query/Referer only as a restrictive scope', () => {
  const context = gateway.extractMobileWorkbenchGatewayRequestContext(
    '/api/v1/capabilities/social-video-refs/runtime-config?workspace_id=workspace-a',
  );
  assert.equal(context.path, '/api/v1/capabilities/social-video-refs/runtime-config');
  assert.equal(context.workspaceId, 'workspace-a');
  assert.equal(context.capabilityCode, 'social_video_refs');
  assert.deepEqual(context.conflicts, []);

  const conflict = gateway.extractMobileWorkbenchGatewayRequestContext(
    '/api/v1/workspaces/workspace-a/tasks',
    {
      referer: 'https://remote-workbench.mindscapeai.app/workspaces/workspace-b/capability-ui-hosts/yogacoach',
    },
    { publicOrigin: 'https://remote-workbench.mindscapeai.app' },
  );
  assert.ok(conflict.conflicts.includes('referer_workspace_mismatch'));
});

test('legacy IG and shared host paths do not invent a capability fallback', () => {
  assert.equal(
    gateway.extractMobileWorkbenchGatewayRequestContext(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=workspace-a',
    ).capabilityCode,
    null,
  );
  assert.equal(
    gateway.extractMobileWorkbenchGatewayRequestContext(
      '/api/v1/host-resources/queue-utilization',
    ).capabilityCode,
    null,
  );
});

test('all repeated query scope values must normalize to one unambiguous context', () => {
  for (const requestUrl of [
    '/workspaces/workspace-a?workspace_id=workspace-a&workspace_id=workspace-b',
    '/workspaces/workspace-a?workspaceId=workspace-a&workspaceId=workspace-b',
    '/workspaces/workspace-a/capability-ui-hosts/yogacoach?capability_code=yogacoach&capability_code=ig',
    '/workspaces/workspace-a/capability-ui-hosts/yogacoach?capabilityCode=yogacoach&capabilityCode=ig',
    '/workspaces/workspace-a?component=WorkspacePage&component=OtherPage',
    '/workspaces/workspace-a?target_capability=yogacoach&target_capability=ig',
    '/workspaces/workspace-a?targetCapability=yogacoach&targetCapability=ig',
    '/workspaces/workspace-a?workspace_id=',
  ]) {
    const context = gateway.extractMobileWorkbenchGatewayRequestContext(requestUrl);
    assert.ok(context.conflicts.length > 0, requestUrl);
  }

  const repeatedSameValue = gateway.extractMobileWorkbenchGatewayRequestContext(
    '/workspaces/workspace-a/capability-ui-hosts/yogacoach'
    + '?workspace_id=workspace-a&workspace_id=workspace-a'
    + '&capabilityCode=yogacoach&capabilityCode=yogacoach'
    + '&component=Workbench&component=Workbench'
    + '&targetCapability=yogacoach&targetCapability=yogacoach',
  );
  assert.deepEqual(repeatedSameValue.conflicts, []);
  assert.equal(repeatedSameValue.workspaceId, 'workspace-a');
  assert.equal(repeatedSameValue.capabilityCode, 'yogacoach');
  assert.equal(repeatedSameValue.componentCode, 'Workbench');
  assert.equal(repeatedSameValue.targetCapabilityCode, 'yogacoach');
});

test('boot assets may inherit explicit same-origin workspace context only', () => {
  const inherited = gateway.extractMobileWorkbenchGatewayRequestContext(
    '/_next/static/chunk.js',
    {
      referer: 'https://remote-workbench.mindscapeai.app/workspaces/workspace-a/capability-ui-hosts/yogacoach',
    },
    { publicOrigin: 'https://remote-workbench.mindscapeai.app' },
  );
  assert.equal(inherited.isBootAsset, true);
  assert.equal(inherited.workspaceId, 'workspace-a');
  assert.equal(inherited.capabilityCode, 'yogacoach');

  const crossOrigin = gateway.extractMobileWorkbenchGatewayRequestContext(
    '/_next/static/chunk.js',
    { referer: 'https://attacker.example/workspaces/workspace-a' },
    { publicOrigin: 'https://remote-workbench.mindscapeai.app' },
  );
  assert.ok(crossOrigin.conflicts.includes('invalid_referer_origin'));

  const postContext = gateway.extractMobileWorkbenchGatewayRequestContext(
    '/_next/static/chunk.js',
    {},
    { requestMethod: 'POST' },
  );
  assert.equal(postContext.isBootAsset, false);

  for (const dynamicPath of [
    '/_next/image?url=%2Fapi%2Fv1%2Fworkspaces%2Fworkspace-a%2Fmedia-assets%2Fasset-1%2Fpreview-content',
    '/_next/data/build/workspaces/workspace-a.json',
    '/_next/webpack-hmr',
  ]) {
    const dynamicContext = gateway.extractMobileWorkbenchGatewayRequestContext(dynamicPath);
    assert.equal(dynamicContext.isBootAsset, false, dynamicPath);
  }
});

test('self-scoped top-level capability documents discard external redirect Referer only', () => {
  for (const requestMethod of ['GET', 'HEAD']) {
    const context = gateway.extractMobileWorkbenchGatewayRequestContext(
      '/workspaces/workspace-a/capability-ui-hosts/yogacoach?component=YogaPracticeWorkbenchPage',
      {
        referer: 'https://shy-resonance-542b.cloudflareaccess.com/cdn-cgi/access/login',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-dest': 'document',
        'sec-fetch-site': 'cross-site',
      },
      {
        publicOrigin: 'https://remote-workbench.mindscapeai.app',
        requestMethod,
      },
    );
    assert.deepEqual(context.conflicts, []);
    assert.equal(context.workspaceId, 'workspace-a');
    assert.equal(context.capabilityCode, 'yogacoach');
    assert.equal('refererPath' in context, false);
  }
});

test('external Referer remains fail-closed outside an exact self-scoped document navigation', () => {
  const externalHeaders = {
    referer: 'https://shy-resonance-542b.cloudflareaccess.com/cdn-cgi/access/login',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-dest': 'document',
  };
  const requestCases = [
    [
      '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
      { referer: externalHeaders.referer, 'sec-fetch-mode': 'navigate' },
      'missing destination',
    ],
    [
      '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
      { ...externalHeaders, 'sec-fetch-mode': ['navigate'] },
      'array header',
    ],
    [
      '/workspaces/workspace-a/capability-ui-hosts/yogacoach/refs',
      externalHeaders,
      'capability subpath',
    ],
    [
      '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
      { ...externalHeaders, connection: 'Upgrade', upgrade: 'websocket' },
      'upgrade request',
    ],
    [
      '/api/v1/capabilities/yogacoach/profile?workspace_id=workspace-a',
      externalHeaders,
      'capability API',
    ],
    [
      '/_next/static/chunk.js',
      externalHeaders,
      'boot asset',
    ],
    [
      '/workspaces/workspace-a/capability-ui-hosts/yogacoach'
        + '?workspace_id=workspace-a&workspace_id=workspace-b',
      externalHeaders,
      'ambiguous scope',
    ],
  ];
  for (const [requestUrl, headers, label] of requestCases) {
    const context = gateway.extractMobileWorkbenchGatewayRequestContext(
      requestUrl,
      headers,
      { publicOrigin: 'https://remote-workbench.mindscapeai.app' },
    );
    assert.ok(context.conflicts.includes('invalid_referer_origin'), label);
  }

  const malformed = gateway.extractMobileWorkbenchGatewayRequestContext(
    '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
    {
      referer: 'not a URL',
      'sec-fetch-mode': 'navigate',
      'sec-fetch-dest': 'document',
    },
    { publicOrigin: 'https://remote-workbench.mindscapeai.app' },
  );
  assert.ok(malformed.conflicts.includes('invalid_referer'));
});

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

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  authorizeRemoteWorkbenchRequest,
} from './mobile-workbench-gateway.mjs';
import {
  createEffectivePolicyPayload,
  createGatewayConfig,
  createPolicyResolution,
  createSignedAccessJwt,
  createTestVerifier,
} from './mobile-workbench-gateway.test-support.mjs';

const config = createGatewayConfig();
const verifier = createTestVerifier();
const headers = {
  host: 'remote-workbench.mindscapeai.app',
  'Cf-Access-Jwt-Assertion': createSignedAccessJwt(),
};

async function authorize(url, resolution, requestMethod = 'GET') {
  return await authorizeRemoteWorkbenchRequest(url, headers, config, {
    requestMethod,
    verifyAccessToken: verifier,
    resolveWorkspaceCapabilityPolicy: async () => resolution,
  });
}

test('global membership never bypasses the workspace capability allowlist', async () => {
  const resolution = createPolicyResolution({
    effectivePayload: createEffectivePolicyPayload({ capabilityCodes: [] }),
  });
  const result = await authorize(
    '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
    resolution,
  );
  assert.equal(result.allowed, false);
  assert.equal(result.reason_code, 'capability_not_allowed');
});

test('installed support must explicitly support the capability', async () => {
  const resolution = createPolicyResolution({ supported: false });
  const result = await authorize(
    '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
    resolution,
  );
  assert.equal(result.allowed, false);
  assert.equal(result.reason_code, 'capability_not_supported');
  assert.equal(result.status_code, 404);
});

test('capability API paths come only from installed support metadata', async () => {
  const allowed = await authorize(
    '/api/v1/capabilities/yogacoach/practice-review?workspace_id=workspace-a',
    createPolicyResolution({
      apiPrefixes: ['/api/v1/capabilities/yogacoach'],
    }),
  );
  assert.equal(allowed.allowed, true);

  const missingPrefix = await authorize(
    '/api/v1/capabilities/yogacoach/practice-review?workspace_id=workspace-a',
    createPolicyResolution({ apiPrefixes: [] }),
  );
  assert.equal(missingPrefix.allowed, false);
  assert.equal(missingPrefix.reason_code, 'capability_path_not_allowed');
});

test('overbroad or reserved capability API roots never become gateway rules', async () => {
  for (const apiPrefix of ['/api/v1', '/api/v1/system-settings', '/api/v1/admin']) {
    const resolution = createPolicyResolution({
      capabilityCode: 'browser_capture',
      effectivePayload: createEffectivePolicyPayload({ capabilityCodes: ['browser_capture'] }),
      apiPrefixes: [apiPrefix],
    });
    const result = await authorize(
      '/api/v1/system-settings/private?workspace_id=workspace-a&capability_code=browser_capture',
      resolution,
      'PUT',
    );
    assert.equal(result.allowed, false);
    assert.equal(result.reason_code, 'capability_path_not_allowed');
  }
});

test('installed and legacy capability assets use the same read-only support decision', async () => {
  const resolution = createPolicyResolution();
  for (const path of [
    '/api/v1/capability-packs/installed-capabilities/yogacoach/ui-assets/1.0.0/component.mjs?workspace_id=workspace-a',
    '/api/v1/capability-packs/yogacoach/ui-assets/1.0.0/component.mjs?workspace_id=workspace-a',
  ]) {
    const allowed = await authorize(path, resolution, 'GET');
    assert.equal(allowed.allowed, true);
    const deniedWrite = await authorize(path, resolution, 'POST');
    assert.equal(deniedWrite.allowed, false);
    assert.equal(deniedWrite.reason_code, 'capability_path_not_allowed');
  }
});

test('legacy shell runtime assets require explicit workspace and capability scope', async () => {
  const scoped = '/__mindscape-capability-host/shell-runtime.browser.js'
    + '?workspace_id=workspace-a&capability_code=yogacoach';
  assert.equal((await authorize(scoped, createPolicyResolution(), 'GET')).allowed, true);
  const missingScope = await authorize(
    '/__mindscape-capability-host/shell-runtime.browser.js',
    createPolicyResolution(),
    'GET',
  );
  assert.equal(missingScope.allowed, false);
  assert.equal(missingScope.reason_code, 'route_workspace_required');
});

test('no IG, Yoga, or Makeup static capability allow path remains', async () => {
  for (const [url, capabilityCode] of [
    ['/api/v1/ig/workbench/sidebar-summary?workspace_id=workspace-a&capability_code=ig', 'ig'],
    ['/api/v1/capabilities/yogacoach/review?workspace_id=workspace-a', 'yogacoach'],
    ['/api/v1/capabilities/makeup_practice_coach/review?workspace_id=workspace-a', 'makeup_practice_coach'],
  ]) {
    const resolution = createPolicyResolution({
      capabilityCode,
      effectivePayload: createEffectivePolicyPayload({ capabilityCodes: [capabilityCode] }),
      apiPrefixes: [],
    });
    const result = await authorize(url, resolution);
    assert.equal(result.allowed, false);
    assert.equal(result.reason_code, 'capability_path_not_allowed');
  }
});

test('shared workspace paths still require membership and use bounded methods', async () => {
  const resolution = createPolicyResolution({ capabilityCode: null });
  const allowed = await authorize('/api/v1/workspaces/workspace-a/tasks', resolution, 'GET');
  assert.equal(allowed.allowed, true);

  const deniedMethod = await authorize('/api/v1/workspaces/workspace-a/tasks', resolution, 'POST');
  assert.equal(deniedMethod.allowed, false);
  assert.equal(deniedMethod.reason_code, 'capability_path_not_allowed');
});

test('workspace media preview remains read-only and membership-gated', async () => {
  const resolution = createPolicyResolution({ capabilityCode: null });
  const path = '/api/v1/workspaces/workspace-a/media-assets/asset-1/preview-content';
  const allowed = await authorize(path, resolution, 'GET');
  assert.equal(allowed.allowed, true);
  const deniedWrite = await authorize(path, resolution, 'POST');
  assert.equal(deniedWrite.allowed, false);

  const outsider = await authorizeRemoteWorkbenchRequest(
    path,
    {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': createSignedAccessJwt({
        claims: { sub: 'subject-outsider', email: 'outsider@example.com' },
      }),
    },
    config,
    {
      requestMethod: 'GET',
      verifyAccessToken: verifier,
      resolveWorkspaceCapabilityPolicy: async () => resolution,
    },
  );
  assert.equal(outsider.allowed, false);
  assert.equal(outsider.reason_code, 'workspace_membership_required');
});

test('public runtime/workspace policy, observability, control UI, and install paths are hidden', async () => {
  const paths = [
    '/settings?tab=remote_workbench_access&workspace_id=workspace-a',
    '/settings/remote-workbench-access?workspace_id=workspace-a',
    '/api/v1/settings/extensions?section=remote-workbench-global-access',
    '/api/v1/settings/extensions?section=remote-workbench-workspace-access&workspace_id=workspace-a',
    '/api/v1/settings/extensions/unowned',
    '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/runtime-policy',
    '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/runtime-policy/',
    '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/workspaces/workspace-a/policy',
    '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/workspaces/workspace-a/policy/',
    '/api/v1/host/services/mobile-workbench-gateway/summary?workspace_id=workspace-a',
    '/api/v1/host/services/mobile-workbench-gateway/audit/',
    '/workspaces/workspace-a/capability-ui-hosts/mindscape_cloud_integration?component=MindscapeMobileWorkbenchGatewayPage',
    '/workspaces/workspace-a/capability-ui-hosts/mindscape_cloud_integration/',
    '/workspaces/workspace-a/capability-ui-hosts/%6dindscape_cloud_integration',
    '/api/v1/capability-packs/install-from-file',
  ];
  for (const path of paths) {
    let resolverCalls = 0;
    const result = await authorizeRemoteWorkbenchRequest(path, headers, config, {
      verifyAccessToken: verifier,
      resolveWorkspaceCapabilityPolicy: async () => {
        resolverCalls += 1;
        return createPolicyResolution();
      },
    });
    assert.equal(result.allowed, false);
    assert.equal(result.status_code, 404);
    assert.equal(result.reason_code, 'remote_control_plane_forbidden');
    assert.equal(resolverCalls, 0);
  }
});

test('resolver error always fails closed', async () => {
  const result = await authorizeRemoteWorkbenchRequest(
    '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
    headers,
    config,
    {
      verifyAccessToken: verifier,
      resolveWorkspaceCapabilityPolicy: async () => {
        throw new Error('backend unavailable');
      },
    },
  );
  assert.equal(result.allowed, false);
  assert.equal(result.reason_code, 'workspace_policy_unavailable');
});

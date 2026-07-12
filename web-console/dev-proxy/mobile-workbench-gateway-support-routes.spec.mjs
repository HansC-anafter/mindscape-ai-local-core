import assert from 'node:assert/strict';
import test from 'node:test';

import {
  authorizeRemoteWorkbenchRequest,
} from './mobile-workbench-gateway.mjs';
import {
  createGatewayConfig,
  createPolicyResolution,
  createSignedAccessJwt,
  createTestVerifier,
} from './mobile-workbench-gateway.test-support.mjs';

const config = createGatewayConfig();
const verifier = createTestVerifier();
const token = createSignedAccessJwt();
const referer =
  'https://remote-workbench.mindscapeai.app/workspaces/workspace-a/capability-ui-hosts/yogacoach';

async function authorize(path, requestMethod = 'GET', includeReferer = true) {
  return await authorizeRemoteWorkbenchRequest(
    path,
    {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': token,
      ...(includeReferer ? { referer } : {}),
    },
    config,
    {
      requestMethod,
      verifyAccessToken: verifier,
      resolveWorkspaceCapabilityPolicy: async () => createPolicyResolution(),
    },
  );
}

test('shared host support routes require workspace context in their own URL', async () => {
  for (const path of [
    '/api/v1/system-settings/keyboard-shortcuts',
    '/api/v1/host-resources/lanes',
    '/api/v1/host-resources/queue-utilization?live=true',
    '/api/v1/host-runtime/status',
  ]) {
    const separator = path.includes('?') ? '&' : '?';
    const explicitContext = await authorize(`${path}${separator}workspace_id=workspace-a`);
    assert.equal(explicitContext.allowed, true);
    for (const includeReferer of [true, false]) {
      const missingContext = await authorize(path, 'GET', includeReferer);
      assert.equal(missingContext.allowed, false);
      assert.equal(missingContext.reason_code, 'route_workspace_required');
    }
  }
});

test('shared read-only routes reject writes', async () => {
  for (const path of [
    '/api/v1/system-settings/keyboard-shortcuts?workspace_id=workspace-a',
    '/api/v1/host-resources/lanes?workspace_id=workspace-a',
    '/api/v1/host-resources/queue-utilization?live=true&workspace_id=workspace-a',
    '/api/v1/workspaces/workspace-a/tasks',
    '/api/v1/workspaces/workspace-a/events/stream',
  ]) {
    const result = await authorize(path, 'POST');
    assert.equal(result.allowed, false);
    assert.equal(result.reason_code, 'capability_path_not_allowed');
  }
});

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

test('host-global support routes stay hidden without resolver reads', async () => {
  let resolverCalls = 0;
  for (const path of [
    '/api/v1/system-settings/keyboard-shortcuts',
    '/api/v1/host-resources/lanes',
    '/api/v1/host-resources/queue-utilization?live=true',
    '/api/v1/host-runtime/status',
  ]) {
    const separator = path.includes('?') ? '&' : '?';
    for (const candidate of [path, `${path}${separator}workspace_id=workspace-a`]) {
      for (const requestMethod of ['GET', 'POST']) {
        const result = await authorizeRemoteWorkbenchRequest(
          candidate,
          {
            host: 'remote-workbench.mindscapeai.app',
            'Cf-Access-Jwt-Assertion': token,
            referer,
          },
          config,
          {
            requestMethod,
            verifyAccessToken: verifier,
            resolveWorkspaceCapabilityPolicy: async () => {
              resolverCalls += 1;
              return createPolicyResolution();
            },
          },
        );
        assert.equal(result.allowed, false, `${requestMethod} ${candidate}`);
        assert.equal(result.status_code, 404, `${requestMethod} ${candidate}`);
        assert.equal(result.reason_code, 'remote_control_plane_forbidden');
      }
    }
  }
  assert.equal(resolverCalls, 0);
});

test('shared read-only routes reject writes', async () => {
  for (const path of [
    '/api/v1/workspaces/workspace-a/tasks',
    '/api/v1/workspaces/workspace-a/events/stream',
  ]) {
    const result = await authorize(path, 'POST');
    assert.equal(result.allowed, false);
    assert.equal(result.reason_code, 'capability_path_not_allowed');
  }
});

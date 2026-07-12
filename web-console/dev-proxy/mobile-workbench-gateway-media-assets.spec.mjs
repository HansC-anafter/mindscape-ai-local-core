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

const mediaPath =
  '/api/v1/capabilities/yogacoach/storage/workspace-a/preview.mp4?workspace_id=workspace-a';

async function authorize(requestMethod) {
  return await authorizeRemoteWorkbenchRequest(
    mediaPath,
    {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': createSignedAccessJwt(),
    },
    createGatewayConfig(),
    {
      requestMethod,
      verifyAccessToken: createTestVerifier(),
      resolveWorkspaceCapabilityPolicy: async () => createPolicyResolution(),
    },
  );
}

test('capability storage media is membership/capability gated and read-only', async () => {
  for (const method of ['GET', 'HEAD', 'OPTIONS']) {
    assert.equal((await authorize(method)).allowed, true);
  }
  const denied = await authorize('POST');
  assert.equal(denied.allowed, false);
  assert.equal(denied.reason_code, 'capability_path_not_allowed');
});

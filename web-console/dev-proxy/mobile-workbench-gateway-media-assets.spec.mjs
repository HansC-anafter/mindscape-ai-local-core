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
const workspacePreviewPath =
  '/api/v1/workspaces/workspace-a/media-assets/artifact-a/preview-data';

async function authorize(requestMethod, requestPath = mediaPath) {
  return await authorizeRemoteWorkbenchRequest(
    requestPath,
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

test('workspace preview data stays shared, membership-gated, and read-only', async () => {
  for (const method of ['GET', 'HEAD', 'OPTIONS']) {
    assert.equal((await authorize(method, workspacePreviewPath)).allowed, true);
  }
  const deniedWrite = await authorize('POST', workspacePreviewPath);
  assert.equal(deniedWrite.allowed, false);
  assert.equal(deniedWrite.reason_code, 'capability_path_not_allowed');

  const policyCalls = [];
  const result = await authorizeRemoteWorkbenchRequest(
    workspacePreviewPath,
    {
      host: 'remote-workbench.mindscapeai.app',
      referer:
        'https://remote-workbench.mindscapeai.app/workspaces/workspace-a/' +
        'capability-ui-hosts/yogacoach',
      'Cf-Access-Jwt-Assertion': createSignedAccessJwt(),
    },
    createGatewayConfig(),
    {
      requestMethod: 'GET',
      verifyAccessToken: createTestVerifier(),
      resolveWorkspaceCapabilityPolicy: async (request) => {
        policyCalls.push(request);
        return createPolicyResolution({ capabilityCode: null });
      },
    },
  );

  assert.equal(result.allowed, true);
  assert.equal(policyCalls.length, 1);
  assert.equal(policyCalls[0].workspaceId, 'workspace-a');
  assert.equal(policyCalls[0].capabilityCode, null);
});

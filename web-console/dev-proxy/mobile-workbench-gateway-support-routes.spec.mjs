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
const token = createSignedAccessJwt();
const referer =
  'https://remote-workbench.mindscapeai.app/workspaces/workspace-a/capability-ui-hosts/yogacoach';

async function authorize(
  path,
  requestMethod = 'GET',
  includeReferer = true,
  resolution = createPolicyResolution(),
) {
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
      resolveWorkspaceCapabilityPolicy: async () => resolution,
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

test('motion profile selection requires one explicit capability and stays read-only', async () => {
  const exactPath =
    '/api/v1/workspaces/workspace-a/motion-reference-profiles/selection';
  for (const requestMethod of ['GET', 'HEAD', 'OPTIONS']) {
    const result = await authorize(
      `${exactPath}?capability_code=yogacoach&source_ref=reference-a`,
      requestMethod,
    );
    assert.equal(result.allowed, true, requestMethod);
  }

  for (const [requestMethod, path, reasonCode] of [
    ['GET', `${exactPath}?source_ref=reference-a`, 'capability_path_not_allowed'],
    ['GET', `${exactPath}?capability_code=yogacoach&capability_code=yogacoach`, 'capability_path_not_allowed'],
    ['GET', `${exactPath}?capability_code=yogacoach&capabilityCode=yogacoach`, 'capability_path_not_allowed'],
    ['GET', `${exactPath}?capability_code=yogacoach&capability_code=dance_motion_coach`, 'request_context_mismatch'],
    ['POST', `${exactPath}?capability_code=yogacoach`, 'capability_path_not_allowed'],
    ['GET', `${exactPath}/artifact-a?capability_code=yogacoach`, 'capability_path_not_allowed'],
  ]) {
    const result = await authorize(path, requestMethod);
    assert.equal(result.allowed, false, `${requestMethod} ${path}`);
    assert.equal(result.reason_code, reasonCode);
  }
});

test('malformed or write profile selection requests stop before policy reads', async () => {
  const exactPath =
    '/api/v1/workspaces/workspace-a/motion-reference-profiles/selection';
  for (const [requestMethod, path] of [
    ['GET', `${exactPath}?source_ref=reference-a`],
    ['GET', `${exactPath}?capability_code=yogacoach&capability_code=yogacoach`],
    ['POST', `${exactPath}?capability_code=yogacoach`],
  ]) {
    let resolverCalls = 0;
    const result = await authorizeRemoteWorkbenchRequest(
      path,
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
    assert.equal(result.allowed, false, `${requestMethod} ${path}`);
    assert.equal(result.reason_code, 'capability_path_not_allowed');
    assert.equal(resolverCalls, 0, `${requestMethod} ${path}`);
  }
});

test('motion profile selection never bypasses capability allowlist or installed support', async () => {
  const path = '/api/v1/workspaces/workspace-a/motion-reference-profiles/selection'
    + '?capability_code=yogacoach&source_ref=reference-a';
  const notAllowed = await authorize(
    path,
    'GET',
    true,
    createPolicyResolution({
      effectivePayload: createEffectivePolicyPayload({ capabilityCodes: [] }),
    }),
  );
  assert.equal(notAllowed.allowed, false);
  assert.equal(notAllowed.reason_code, 'capability_not_allowed');

  const unsupported = await authorize(
    path,
    'GET',
    true,
    createPolicyResolution({ supported: false }),
  );
  assert.equal(unsupported.allowed, false);
  assert.equal(unsupported.reason_code, 'capability_not_supported');
});

test('device-link media routes allow only the remote camera lifecycle methods', async () => {
  for (const [requestMethod, path] of [
    ['GET', '/api/v1/workspaces/workspace-a/device-bindings/sessions'],
    ['POST', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions'],
    ['GET', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions'],
    ['POST', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions/media-session/refresh'],
    ['POST', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions/media-session/receiver/start'],
    ['POST', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions/media-session/stop'],
  ]) {
    const result = await authorize(path, requestMethod);
    assert.equal(result.allowed, true, `${requestMethod} ${path}`);
  }

  for (const [requestMethod, path] of [
    ['POST', '/api/v1/workspaces/workspace-a/device-bindings/sessions'],
    ['DELETE', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions'],
    ['GET', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions/media-session/stop'],
    ['POST', '/api/v1/workspaces/workspace-a/device-bindings/device-session/media-sessions/media-session/receiver/events'],
  ]) {
    const result = await authorize(path, requestMethod);
    assert.equal(result.allowed, false, `${requestMethod} ${path}`);
    assert.equal(result.reason_code, 'capability_path_not_allowed');
  }
});

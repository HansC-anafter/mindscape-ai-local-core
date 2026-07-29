import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';

import {
  authorizeRemoteWorkbenchRequest,
  createCloudflareAccessJwtVerifier,
  loadMobileWorkbenchGatewayRuntimeConfig,
} from './mobile-workbench-gateway.mjs';
import {
  ACCESS_AUDIENCE,
  ACCESS_ISSUER,
  ACCESS_KEY_ID,
  ACCESS_PUBLIC_KEY,
  AUTH_CONFIG_FINGERPRINT,
  createGatewayConfig,
  createPolicyResolution,
  createRuntimePolicyPayload,
  createSignedAccessJwt,
  createTestVerifier,
  jsonResponse,
} from './mobile-workbench-gateway.test-support.mjs';

const REQUEST_URL = '/workspaces/workspace-a/capability-ui-hosts/yogacoach';

async function authorizeWith({
  token = createSignedAccessJwt(),
  verifier = createTestVerifier(),
  config = createGatewayConfig(),
  resolver = async () => createPolicyResolution(),
  headerName = 'Cf-Access-Jwt-Assertion',
} = {}) {
  let resolverCalls = 0;
  const result = await authorizeRemoteWorkbenchRequest(
    REQUEST_URL,
    token === null
      ? { host: 'remote-workbench.mindscapeai.app' }
      : { host: 'remote-workbench.mindscapeai.app', [headerName]: token },
    config,
    {
      verifyAccessToken: verifier,
      resolveWorkspaceCapabilityPolicy: async (input) => {
        resolverCalls += 1;
        return await resolver(input);
      },
    },
  );
  return { result, resolverCalls };
}

test('startup reads the exact runtime auth config once before marking the listener ready', async () => {
  let fetchCalls = 0;
  const config = await loadMobileWorkbenchGatewayRuntimeConfig({
    env: {
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app',
    },
    buildInternalApiUrl: (path) => `http://backend.test${path}`,
    fetchImpl: async (url, options) => {
      fetchCalls += 1;
      assert.equal(options.method, 'GET');
      assert.match(url, /mobile-workbench-gateway\/runtime-policy$/);
      return jsonResponse(createRuntimePolicyPayload());
    },
  });

  assert.equal(fetchCalls, 1);
  assert.equal(config.startupFetchCount, 1);
  assert.equal(config.remoteListenerReady, true);
  assert.equal(config.authConfigSource, 'runtime_policy');
  assert.equal(config.authConfigFingerprint, AUTH_CONFIG_FINGERPRINT);
  assert.equal(config.runtimePolicy.accessIssuer, ACCESS_ISSUER);
  assert.equal(config.runtimePolicy.accessAudience, ACCESS_AUDIENCE);
});

test('missing runtime auth values fail closed without retry', async () => {
  let fetchCalls = 0;
  const config = await loadMobileWorkbenchGatewayRuntimeConfig({
    env: {
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app',
    },
    buildInternalApiUrl: (path) => `http://backend.test${path}`,
    fetchImpl: async () => {
      fetchCalls += 1;
      return jsonResponse(createRuntimePolicyPayload({
        issuer: null,
        audience: null,
        fingerprint: null,
        state: 'enrollment_only',
        administrators: [],
        source: 'default_deny',
        revision: 0,
      }));
    },
  });

  assert.equal(fetchCalls, 1);
  assert.equal(config.startupFetchCount, 1);
  assert.equal(config.remoteListenerReady, false);
  assert.deepEqual(config.errors, []);
  assert.equal(config.authConfigSource, 'runtime_policy');
  assert.equal(config.authConfigFingerprint, null);
  assert.equal(config.remoteAccessState, 'enrollment_only');
  assert.equal(config.jwtIssuerReady, false);
  assert.equal(config.jwtAudienceReady, false);
});

test('partial-null and enforced-null runtime auth config are malformed', async () => {
  for (const payload of [
    createRuntimePolicyPayload({
      issuer: null,
      audience: ACCESS_AUDIENCE,
      fingerprint: null,
      state: 'enrollment_only',
    }),
    createRuntimePolicyPayload({
      issuer: null,
      audience: null,
      fingerprint: null,
      state: 'enforced',
    }),
  ]) {
    const config = await loadMobileWorkbenchGatewayRuntimeConfig({
      env: {
        MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
        MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app',
      },
      buildInternalApiUrl: (path) => `http://backend.test${path}`,
      fetchImpl: async () => jsonResponse(payload),
    });
    assert.equal(config.remoteListenerReady, false);
    assert.match(config.errors[0], /runtime_access_policy_load_failed/);
  }
});

test('runtime source and grants are absolutely coherent before listener open', async () => {
  const malformedPayloads = [
    createRuntimePolicyPayload({ source: 'default_deny' }),
    createRuntimePolicyPayload({
      issuer: null,
      audience: null,
      fingerprint: null,
      state: 'enrollment_only',
      source: 'default_deny',
      administrators: [{
        subject: 'pending_identity_resolution',
        email: 'hans@anafter.co',
        status: 'pending',
      }],
    }),
  ];
  for (const payload of malformedPayloads) {
    const config = await loadMobileWorkbenchGatewayRuntimeConfig({
      env: {
        MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
        MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app',
      },
      buildInternalApiUrl: (path) => `http://backend.test${path}`,
      fetchImpl: async () => jsonResponse(payload),
    });
    assert.equal(config.remoteListenerReady, false);
    assert.match(config.errors[0], /runtime_access_policy_load_failed/);
  }
});

test('verified invite self-service bypasses membership only on two exact routes', async () => {
  const config = createGatewayConfig();
  const verifier = createTestVerifier();
  const headers = {
    host: 'remote-workbench.mindscapeai.app',
    'cf-access-jwt-assertion': createSignedAccessJwt({
      claims: {
        sub: 'invited-subject',
        email: 'invited@example.com',
      },
    }),
  };
  const page = await authorizeRemoteWorkbenchRequest(
    '/access/invitations/accept',
    headers,
    config,
    { requestMethod: 'GET', verifyAccessToken: verifier },
  );
  const post = await authorizeRemoteWorkbenchRequest(
    '/api/v1/access-control/invitations/accept',
    headers,
    config,
    { requestMethod: 'POST', verifyAccessToken: verifier },
  );
  const wrongMethod = await authorizeRemoteWorkbenchRequest(
    '/api/v1/access-control/invitations/accept',
    headers,
    config,
    { requestMethod: 'GET', verifyAccessToken: verifier },
  );

  assert.equal(page.allowed, true);
  assert.equal(post.allowed, true);
  assert.equal(page.invitation_acceptance, true);
  assert.deepEqual(post.verified_principal, {
    provider: 'cloudflare-access',
    issuer: ACCESS_ISSUER,
    subject: 'invited-subject',
    email: 'invited@example.com',
  });
  assert.equal(wrongMethod.allowed, false);
});

test('enabled startup requires the one exact public origin before listener open', async () => {
  const invalidOrigins = [
    undefined,
    'http://remote-workbench.mindscapeai.app',
    'https://user@remote-workbench.mindscapeai.app',
    'https://remote-workbench.mindscapeai.app:443',
    'https://remote-workbench.mindscapeai.app/',
    'https://remote-workbench.mindscapeai.app/path',
    'https://remote-workbench.mindscapeai.app?query=1',
    'https://remote-workbench.mindscapeai.app#fragment',
    'https://other.example',
  ];
  for (const publicOrigin of invalidOrigins) {
    let fetchCalls = 0;
    const config = await loadMobileWorkbenchGatewayRuntimeConfig({
      env: {
        MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
        ...(publicOrigin === undefined
          ? {}
          : { MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: publicOrigin }),
      },
      buildInternalApiUrl: (path) => `http://backend.test${path}`,
      fetchImpl: async () => {
        fetchCalls += 1;
        return jsonResponse(createRuntimePolicyPayload());
      },
    });
    assert.equal(fetchCalls, 1);
    assert.equal(config.remoteListenerReady, false);
    assert.match(config.errors[0], /mobile_workbench_public_origin/);
  }
});

test('only Cf-Access-Jwt-Assertion is accepted', async () => {
  const { result, resolverCalls } = await authorizeWith({ headerName: 'CF-Authorization' });
  assert.equal(result.allowed, false);
  assert.equal(result.reason_code, 'missing_access_token');
  assert.equal(result.verification_stage, 'identity_rejected');
  assert.equal(resolverCalls, 0);
});

test('strict JWT negative matrix denies before policy resolution', async (t) => {
  const otherKeyPair = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const now = 1_800_000_000;
  const cases = [
    ['missing token', null, createTestVerifier()],
    ['malformed token', 'not-a-jwt', createTestVerifier()],
    ['forged signature', createSignedAccessJwt({ privateKey: otherKeyPair.privateKey }), createTestVerifier()],
    ['alg none', createSignedAccessJwt({ header: { alg: 'none' } }), createTestVerifier()],
    ['wrong kid', createSignedAccessJwt({ header: { kid: 'unknown-key' } }), createTestVerifier()],
    ['wrong issuer', createSignedAccessJwt({ claims: { iss: 'https://other.cloudflareaccess.com' } }), createTestVerifier()],
    ['wrong audience', createSignedAccessJwt({ claims: { aud: 'wrong-audience' } }), createTestVerifier()],
    ['empty audiences', createSignedAccessJwt({ claims: { aud: [] } }), createTestVerifier()],
    ['multiple audiences', createSignedAccessJwt({ claims: { aud: [ACCESS_AUDIENCE, 'other'] } }), createTestVerifier()],
    ['duplicate audiences', createSignedAccessJwt({ claims: { aud: [ACCESS_AUDIENCE, ACCESS_AUDIENCE] } }), createTestVerifier()],
    ['non-string audience', createSignedAccessJwt({ claims: { aud: 42 } }), createTestVerifier()],
    ['HS256 algorithm', createSignedAccessJwt({ header: { alg: 'HS256' } }), createTestVerifier()],
    ['wrong type', createSignedAccessJwt({ claims: { type: 'org' } }), createTestVerifier()],
    ['missing exp', createSignedAccessJwt({ claims: { exp: undefined } }), createTestVerifier()],
    ['expired exp', createSignedAccessJwt({ claims: { exp: now - 60 } }), createTestVerifier()],
    ['missing nbf', createSignedAccessJwt({ claims: { nbf: undefined } }), createTestVerifier()],
    ['future nbf', createSignedAccessJwt({ claims: { nbf: now + 60 } }), createTestVerifier()],
    ['nbf after exp', createSignedAccessJwt({ claims: { nbf: now + 30, exp: now + 29 } }), createTestVerifier()],
    ['missing iat', createSignedAccessJwt({ claims: { iat: undefined } }), createTestVerifier()],
    ['future iat', createSignedAccessJwt({ claims: { iat: now + 60 } }), createTestVerifier()],
    ['iat after exp', createSignedAccessJwt({ claims: { iat: now + 30, exp: now + 29 } }), createTestVerifier()],
    ['missing subject', createSignedAccessJwt({ claims: { sub: '' } }), createTestVerifier()],
  ];

  for (const [name, token, verifier] of cases) {
    await t.test(name, async () => {
      const { result, resolverCalls } = await authorizeWith({ token, verifier });
      assert.equal(result.allowed, false);
      assert.equal(result.status_code, 403);
      assert.equal(result.verification_stage, 'identity_rejected');
      assert.equal(resolverCalls, 0);
    });
  }
});

test('JWK timeout fails closed before policy resolution', async () => {
  const verifier = createCloudflareAccessJwtVerifier({
    accessIssuer: ACCESS_ISSUER,
    accessAudience: ACCESS_AUDIENCE,
    now: () => 1_800_000_000_000,
    fetchImpl: async (_url, { signal }) => await new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      });
    }),
  });
  const { result, resolverCalls } = await authorizeWith({ verifier });
  assert.equal(result.allowed, false);
  assert.equal(result.reason_code, 'access_signing_key_timeout');
  assert.equal(resolverCalls, 0);
});

test('a strict singleton-array audience token reaches the resolver once', async () => {
  const { result, resolverCalls } = await authorizeWith();
  assert.equal(result.allowed, true);
  assert.equal(result.verification_stage, 'principal_verified');
  assert.equal(resolverCalls, 1);
  assert.deepEqual(result.grant_sources, ['local_core_super_admin']);
});

test('a strict scalar audience token remains compatible', async () => {
  const { result, resolverCalls } = await authorizeWith({
    token: createSignedAccessJwt({ claims: { aud: ACCESS_AUDIENCE } }),
  });
  assert.equal(result.allowed, true);
  assert.equal(result.verification_stage, 'principal_verified');
  assert.equal(resolverCalls, 1);
});

test('unknown kid cooldown limits JWK refresh without a timer', async () => {
  let fetchCalls = 0;
  const publicJwk = {
    ...ACCESS_PUBLIC_KEY.export({ format: 'jwk' }),
    kid: ACCESS_KEY_ID,
    alg: 'RS256',
    use: 'sig',
  };
  const verifier = createCloudflareAccessJwtVerifier({
    accessIssuer: ACCESS_ISSUER,
    accessAudience: ACCESS_AUDIENCE,
    now: () => 1_800_000_000_000,
    fetchImpl: async () => {
      fetchCalls += 1;
      return jsonResponse({ keys: [publicJwk] });
    },
  });
  const unknownKidToken = createSignedAccessJwt({ header: { kid: 'rotated-unknown' } });
  await verifier(unknownKidToken);
  await verifier(unknownKidToken);
  assert.equal(fetchCalls, 1);
});

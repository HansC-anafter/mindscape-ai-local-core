import crypto from 'node:crypto';
import http from 'node:http';

import {
  createCapabilityGatewayPathRules,
} from './mobile-workbench-gateway-capability-rules.mjs';

import {
  createCloudflareAccessJwtVerifier,
  deriveAuthConfigFingerprint,
  normalizeEffectiveWorkspacePolicy,
  normalizeRuntimeAccessPolicy,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.mjs';

export const ACCESS_ISSUER = 'https://shy-resonance-542b.cloudflareaccess.com';
export const ACCESS_AUDIENCE = '94cce07bfe76d9b3903ee15316df231bb6b0c004e0a68114b8e965b2710e8b1f';
export const AUTH_CONFIG_FINGERPRINT =
  '76be8177018ba0784dba95deb74fa344b127482ebaa500de91276840733b8c07';
export const ACCESS_KEY_ID = 'remote-workbench-test-key';

const KEY_PAIR = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
export const ACCESS_PRIVATE_KEY = KEY_PAIR.privateKey;
export const ACCESS_PUBLIC_KEY = KEY_PAIR.publicKey;
export const ACCESS_PUBLIC_JWK = {
  ...ACCESS_PUBLIC_KEY.export({ format: 'jwk' }),
  kid: ACCESS_KEY_ID,
  alg: 'RS256',
  use: 'sig',
};

export function base64urlEncode(value) {
  return Buffer.from(value).toString('base64url');
}

export function createSignedAccessJwt({
  claims = {},
  header = {},
  privateKey = ACCESS_PRIVATE_KEY,
  nowEpochSeconds = 1_800_000_000,
} = {}) {
  const tokenHeader = {
    alg: 'RS256',
    typ: 'JWT',
    kid: ACCESS_KEY_ID,
    ...header,
  };
  const payload = {
    iss: ACCESS_ISSUER,
    aud: ACCESS_AUDIENCE,
    type: 'app',
    exp: nowEpochSeconds + 3600,
    nbf: nowEpochSeconds - 30,
    iat: nowEpochSeconds - 30,
    sub: 'subject-global-a',
    email: 'hans@anafter.co',
    ...claims,
  };
  const signingInput = `${base64urlEncode(JSON.stringify(tokenHeader))}.${base64urlEncode(JSON.stringify(payload))}`;
  const signature = crypto.sign('RSA-SHA256', Buffer.from(signingInput), privateKey);
  return `${signingInput}.${base64urlEncode(signature)}`;
}

export function createRuntimePolicyPayload({
  state = 'enforced',
  administrators = [
    { subject: 'subject-global-a', email: 'hans@anafter.co', status: 'active' },
    { subject: 'subject-global-b', email: 'pproo.reader@gmail.com', status: 'active' },
  ],
  issuer = ACCESS_ISSUER,
  audience = ACCESS_AUDIENCE,
  fingerprint = AUTH_CONFIG_FINGERPRINT,
  revision = 2,
  source = 'persisted_policy',
} = {}) {
  return {
    id: 'remote-workbench-runtime',
    access_issuer: issuer,
    access_audience: audience,
    auth_config_fingerprint: fingerprint,
    auth_config_source: 'runtime_policy',
    remote_access_state: state,
    local_core_super_admins: administrators,
    revision,
    updated_by: 'local-operator',
    created_at: '2026-07-13T00:00:00Z',
    updated_at: '2026-07-13T00:00:00Z',
    source,
  };
}

export function createGatewayConfig(options = {}) {
  const runtimePolicy = normalizeRuntimeAccessPolicy(createRuntimePolicyPayload(options));
  return resolveMobileWorkbenchGatewayConfig({
    MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app',
  }, runtimePolicy, { startupFetchCount: 1 });
}

export function createEffectivePolicyPayload({
  workspaceId = 'workspace-a',
  state = 'enforced',
  administrators = [
    { subject: 'subject-global-a', email: 'hans@anafter.co', status: 'active' },
    { subject: 'subject-global-b', email: 'pproo.reader@gmail.com', status: 'active' },
  ],
  directPrincipals = [],
  effectivePrincipals = [
    {
      subject: 'subject-global-a',
      email: 'hans@anafter.co',
      grant_sources: ['local_core_super_admin'],
    },
    {
      subject: 'subject-global-b',
      email: 'pproo.reader@gmail.com',
      grant_sources: ['local_core_super_admin'],
    },
  ],
  capabilityCodes = ['yogacoach'],
  fingerprint = AUTH_CONFIG_FINGERPRINT,
} = {}) {
  return {
    workspace_id: workspaceId,
    access_issuer: ACCESS_ISSUER,
    access_audience: ACCESS_AUDIENCE,
    auth_config_fingerprint: fingerprint,
    auth_config_source: 'runtime_policy',
    remote_access_state: state,
    runtime_policy_revision: 2,
    runtime_policy_source: 'persisted_policy',
    local_core_super_admins: administrators,
    allowed_principals: directPrincipals,
    effective_principals: effectivePrincipals,
    allowed_capability_codes: capabilityCodes,
    workspace_policy_source: 'persisted_policy',
    updated_by: 'local-operator',
    created_at: '2026-07-13T00:00:00Z',
    updated_at: '2026-07-13T00:00:00Z',
    source: 'effective_policy',
  };
}

export function createPolicyResolution({
  workspaceId = 'workspace-a',
  capabilityCode = 'yogacoach',
  effectivePayload = createEffectivePolicyPayload({ workspaceId }),
  supported = true,
  apiPrefixes = ['/api/v1/capabilities/yogacoach'],
} = {}) {
  const effectivePolicy = normalizeEffectiveWorkspacePolicy(effectivePayload, workspaceId);
  const hostRouteTemplate = capabilityCode
    ? `/workspaces/{workspaceId}/capability-ui-hosts/${capabilityCode}`
    : null;
  return {
    effectivePolicy,
    capabilitySupport: capabilityCode
      ? {
          capabilityCode,
          supported,
          hasUiComponents: supported,
          hostRouteTemplate: supported ? hostRouteTemplate : null,
          mainPageComponentCodes: supported ? ['TestWorkbenchPage'] : [],
          requestScopeContract: supported ? 'explicit_workspace_v1' : null,
          apiPrefixes,
        }
      : null,
    capabilityCode,
    capabilityAllowed: capabilityCode
      ? effectivePolicy.allowedCapabilityCodes.includes(capabilityCode)
      : true,
    allowedPathRules: capabilityCode
      ? createCapabilityGatewayPathRules({
          capabilityCode,
          hostRouteTemplate: supported ? hostRouteTemplate : null,
          apiPrefixes,
        })
      : [],
  };
}

export function createTestVerifier({
  nowEpochSeconds = 1_800_000_000,
  publicKey = ACCESS_PUBLIC_KEY,
} = {}) {
  return createCloudflareAccessJwtVerifier({
    accessIssuer: ACCESS_ISSUER,
    accessAudience: ACCESS_AUDIENCE,
    now: () => nowEpochSeconds * 1000,
    resolveSigningKey: async (kid) => {
      if (kid !== ACCESS_KEY_ID) {
        throw new Error('unknown_access_token_kid');
      }
      return publicKey;
    },
  });
}

export function jsonResponse(payload, { status = 200, headers = {} } = {}) {
  const body = JSON.stringify(payload);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) => String(name).toLowerCase() === 'content-length'
        ? String(Buffer.byteLength(body))
        : headers[String(name).toLowerCase()] || null,
    },
    text: async () => body,
  };
}

export function requestLoopback(url, options = {}) {
  const target = new URL(url);
  const body = options.body == null ? null : Buffer.from(String(options.body));
  const headers = Object.fromEntries(new Headers(options.headers).entries());
  if (body && headers['content-length'] == null) {
    headers['content-length'] = String(body.length);
  }
  return new Promise((resolve, reject) => {
    const request = http.request({
      hostname: target.hostname,
      port: target.port,
      path: `${target.pathname}${target.search}`,
      method: options.method || 'GET',
      headers,
    }, (response) => {
      const chunks = [];
      response.on('data', (chunk) => chunks.push(chunk));
      response.on('end', () => {
        resolve(new Response(Buffer.concat(chunks), {
          status: response.statusCode,
          headers: response.headers,
        }));
      });
    });
    request.on('error', reject);
    if (body) request.write(body);
    request.end();
  });
}

if (deriveAuthConfigFingerprint(ACCESS_ISSUER, ACCESS_AUDIENCE) !== AUTH_CONFIG_FINGERPRINT) {
  throw new Error('test auth config fingerprint fixture is invalid');
}

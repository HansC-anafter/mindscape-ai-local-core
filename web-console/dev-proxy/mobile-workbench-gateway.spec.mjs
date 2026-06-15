import crypto from 'node:crypto';
import { describe, expect, it } from 'vitest';

import {
  extractMobileWorkbenchGatewayRequestContext,
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.mjs';

const RSA_KEY_PAIR = crypto.generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: {
    type: 'spki',
    format: 'pem',
  },
  privateKeyEncoding: {
    type: 'pkcs1',
    format: 'pem',
  },
});

function base64urlEncode(value) {
  return Buffer.from(value)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function createSignedAccessJwt(payload = {}, privateKey = RSA_KEY_PAIR.privateKey) {
  const header = base64urlEncode(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
  const body = base64urlEncode(JSON.stringify(payload));
  const signingInput = `${header}.${body}`;
  const signature = crypto.createSign('RSA-SHA256')
    .update(signingInput)
    .end()
    .sign(privateKey);
  return `${signingInput}.${base64urlEncode(signature)}`;
}

function createAccessJwt(payload = {}) {
  const header = Buffer.from(JSON.stringify({ alg: 'none', typ: 'JWT' }))
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  const body = Buffer.from(JSON.stringify(payload))
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  return `${header}.${body}.sig`;
}

describe('mobile workbench gateway', () => {
  it('keeps gateway disabled unless explicitly enabled', () => {
    expect(resolveMobileWorkbenchGatewayConfig({})).toMatchObject({
      enabled: false,
      reason: 'disabled',
      errors: [],
    });
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/admin/secret', resolveMobileWorkbenchGatewayConfig({}))).toBe(true);
    expect(
      isMobileWorkbenchGatewayRequestAllowed('/api/v1/admin/secret', {}, resolveMobileWorkbenchGatewayConfig({})).allowed,
    ).toBe(true);
  });

  it('accepts a canonical public origin and rejects loopback public origins', () => {
    expect(resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app/',
    })).toMatchObject({
      enabled: true,
      reason: 'enabled',
      publicOrigin: 'https://remote-workbench.mindscapeai.app',
      errors: [],
    });

    expect(resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'http://localhost:8300',
    })).toMatchObject({
      enabled: true,
      reason: 'enabled_with_invalid_rules',
      publicOrigin: 'http://localhost:8300',
      errors: ['MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN_must_use_https'],
    });

    expect(resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://127.0.0.1:8300',
    })).toMatchObject({
      enabled: true,
      reason: 'enabled_with_invalid_rules',
      publicOrigin: 'https://127.0.0.1:8300',
      errors: ['MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN_must_not_use_loopback_host'],
    });
  });

  it('keeps the loopback desktop control plane outside the mobile allowlist', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'admin@mindscape.ai',
    });

    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/workspaces/ws-1?tool=motion_source',
      { host: 'localhost:8300' },
      config,
    )).toMatchObject({
      allowed: true,
      ingress: 'local_control_plane',
    });
    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/admin/secret',
      { host: '127.0.0.1:8300' },
      config,
    )).toMatchObject({
      allowed: true,
      ingress: 'local_control_plane',
    });
    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/workspaces/ws-1?tool=motion_source',
      { host: '192.168.0.104:8300' },
      config,
    )).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
    });
  });

  it('allows only bounded device-link ingress paths with the process-local token', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'admin@mindscape.ai',
    });
    const ingressToken = 'test-device-link-ingress-token';
    const headers = {
      'x-mindscape-device-link-ingress-token': ingressToken,
    };

    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/device-link/PAIR1234?workspaceId=ws-1&sourceMode=phone',
      headers,
      config,
      { deviceLinkIngressToken: ingressToken },
    )).toMatchObject({
      allowed: true,
      ingress: 'device_link_https',
    });
    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-1/device-bindings/PAIR1234/control',
      headers,
      config,
      { deviceLinkIngressToken: ingressToken },
    )).toMatchObject({
      allowed: true,
      ingress: 'device_link_https',
    });
    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/admin/secret',
      headers,
      config,
      { deviceLinkIngressToken: ingressToken },
    )).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
    });
    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/device-link/PAIR1234',
      { 'x-mindscape-device-link-ingress-token': 'wrong-token' },
      config,
      { deviceLinkIngressToken: ingressToken },
    )).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
    });
  });

  it('allows bounded IG, YogaCoach, and Makeup Practice Coach support paths by default when enabled', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });
    expect(config).toMatchObject({
      enabled: true,
      reason: 'enabled',
      errors: [],
      allowedPathRules: expect.any(Array),
      extraAllowedPathRules: [],
      allowlistEmails: [],
      allowlistGroups: [],
      workspaceAllowlist: [],
    });

    expect(isMobileWorkbenchGatewayPathAllowed('/workspaces/ws-1/capability-ui-hosts/ig', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/workspaces/ws-1/capability-ui-hosts/ig?component=IGWorkbenchPage', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/ig/workbench/sidebar-summary', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/installed-capabilities', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/installed-capabilities/ig', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/installed-capabilities/ig/ui-components', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/installed-capabilities/ig/workspace-tools', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/installed-capabilities/ig/ui-assets/bundle.js', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/workspaces/ws-1/executions?limit=50', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/workspaces/ws-1/summary', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/ig/ui-assets/bundle.js', config)).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/workspaces/ws-1/capability-ui-hosts/makeup_practice_coach',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capabilities/makeup_practice_coach/acceptance/practice-loop',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capability-packs/installed-capabilities/makeup_practice_coach',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capability-packs/installed-capabilities/makeup_practice_coach/ui-components',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capability-packs/installed-capabilities/makeup_practice_coach/ui-assets/0.6.0/components/MpcFaceChartWorkbenchPage.mjs',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/workspaces/ws-1/capability-ui-hosts/yogacoach',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capabilities/yogacoach/practice-review/projection',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capability-packs/installed-capabilities/yogacoach',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capability-packs/installed-capabilities/yogacoach/ui-components',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capability-packs/installed-capabilities/yogacoach/ui-assets/1.0.0/components/YogaPracticeWorkbenchPage.mjs',
        config,
      ),
    ).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/other-service/route', config)).toBe(false);
    expect(isMobileWorkbenchGatewayPathAllowed('/workspaces/ws-1/capability-ui-hosts/performance_direction', config)).toBe(false);
  });

  it('allows bounded workspace device-binding contracts and extracts workspace context', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const headers = { 'cf-access-jwt-assertion': token };

    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-1/device-bindings/control',
      headers,
      config,
    )).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
      },
    });
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/device-bindings/pairing-codes',
      config,
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/device-bindings/session-1/media-sessions/session-1/signal',
      config,
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/device-bindings/session-1/arbitrary',
      config,
    )).toBe(false);
  });

  it('supports extra allowlist prefixes and regex tokens', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_EXTRA_PATH_RULES: '/api/v1/admin/preview,regex:^/custom-gateway/.+',
    });

    expect(config.errors).toHaveLength(0);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/admin/preview/health', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/custom-gateway/abc/def', config)).toBe(true);
  });

  it('checks access token presence when policy allowlists are configured', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'a@mindscape.ai',
    });
    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/workspaces/ws-1/capability-ui-hosts/ig?component=IGWorkbenchPage',
      {},
      config,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'missing_access_token',
      status_code: 403,
    });
  });

  it('allows requests when access token email is allowlisted', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'a@mindscape.ai,b@mindscape.ai',
    });
    const token = createAccessJwt({
      email: 'a@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
      groups: ['everyone'],
      workspace_id: 'ws-1',
    });
    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/workspaces/ws-1/capability-ui-hosts/ig?component=IGWorkbenchPage',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: true,
      status_code: 200,
      policy_enabled: true,
      claims_email: 'a@mindscape.ai',
    });
  });

  it('denies requests when group is not allowlisted', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_GROUPS: 'ops,infra',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'trusted@mindscape.ai',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
      groups: ['design'],
      workspace_id: 'ws-1',
    });
    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=ws-1',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'email_not_allowed',
      status_code: 403,
    });
  });

  it('uses audience and issuer claims when configured', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE: 'remote-workbench',
      MOBILE_WORKBENCH_GATEWAY_JWT_ISSUER: 'https://identity.mindscape.ai',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
      aud: 'remote-workbench',
      iss: 'https://identity.mindscape.ai',
    });

    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=ws-1',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: true,
      status_code: 200,
      policy_enabled: true,
      reason: 'mobile_workbench_gateway_request_allowed',
    });
  });

  it('rejects tokens failing audience enforcement', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE: 'remote-workbench',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
      aud: 'other-service',
    });

    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=ws-1',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'invalid_access_token_audience',
      status_code: 403,
    });
  });

  it('rejects tokens failing issuer enforcement', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_JWT_ISSUER: 'https://identity.mindscape.ai',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
      iss: 'https://other-idp.example.com',
    });

    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=ws-1',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'invalid_access_token_issuer',
      status_code: 403,
    });
  });

  it('verifies token signature when public key verification is required', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION: '1',
      MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY: RSA_KEY_PAIR.publicKey,
    });
    const token = createSignedAccessJwt({
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=ws-1',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: true,
      status_code: 200,
    });
  });

  it('rejects token when signature verification is enabled but signature is invalid', () => {
    const maliciousKeyPair = crypto.generateKeyPairSync('rsa', {
      modulusLength: 2048,
      publicKeyEncoding: {
        type: 'spki',
        format: 'pem',
      },
      privateKeyEncoding: {
        type: 'pkcs1',
        format: 'pem',
      },
    });
    const validConfig = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE: 'remote-workbench',
      MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION: '1',
      MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY: RSA_KEY_PAIR.publicKey,
    });
    const badToken = createSignedAccessJwt(
      {
        aud: 'remote-workbench',
        exp: Math.floor(Date.now() / 1000) + 3600,
      },
      maliciousKeyPair.privateKey,
    );

    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=ws-1',
      {
        'cf-access-jwt-assertion': badToken,
      },
      validConfig,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'invalid_access_token_signature',
      status_code: 403,
    });
  });

  it('returns config error when signature verification requires key but key is missing', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION: '1',
    });

    expect(config).toMatchObject({
      reason: 'enabled_with_invalid_rules',
      jwtVerifyEnabled: false,
    });
    expect(config.errors).toContain(
      'MOBILE_WORKBENCH_GATEWAY_JWT_SIGNATURE_VERIFICATION_ENABLED_BUT_PUBLIC_KEY_missing',
    );
  });

  it('denies access when signature verification is required but key is missing', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION: '1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/ig/workbench/sidebar-summary?workspace_id=ws-1',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason_code: 'MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_required_for_signature_verification',
      status_code: 403,
    });
  });

  it('supports workspace allowlist enforcement for routed requests', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
      workspace_id: 'ws-2',
    });
    const workspacePathResult = isMobileWorkbenchGatewayRequestAllowed(
      '/workspaces/ws-2/capability-ui-hosts/ig?component=IGWorkbenchPage',
      {
        'CF-Authorization': `Bearer ${token}`,
      },
      config,
    );

    expect(workspacePathResult).toMatchObject({
      allowed: false,
      reason_code: 'workspace_not_allowed',
      status_code: 403,
    });
  });

  it('does not apply workspace allowlist to unscoped Next.js and pack support resources', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'user@mindscape.ai',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const headers = {
      'cf-access-jwt-assertion': token,
    };

    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/_next/static/chunks/app/workspaces/%5BworkspaceId%5D/capability-ui-hosts/%5BcapabilityCode%5D/%5B%5B...surfacePath%5D%5D/page.js',
      headers,
      config,
    )).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        workspaceId: null,
        capabilityCode: null,
      },
    });

    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/capability-packs/installed-capabilities/ig/ui-components',
      headers,
      config,
    )).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        workspaceId: null,
        capabilityCode: 'ig',
      },
    });

    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/workspaces/ws-2/capability-ui-hosts/ig?component=IGWorkbenchPage',
      headers,
      config,
    )).toMatchObject({
      allowed: false,
      reason_code: 'workspace_not_allowed',
      status_code: 403,
    });
  });

  it('uses execution path workspace context when claims do not include workspace metadata', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const allowed = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-1/executions?limit=50&status=running',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(allowed).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'ig',
      },
    });

    const denied = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-2/executions?limit=50&status=running',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(denied).toMatchObject({
      allowed: false,
      reason_code: 'workspace_not_allowed',
      status_code: 403,
      context: {
        workspaceId: 'ws-2',
      },
    });
  });

  it('uses workspace summary path context for workspace allowlist checks', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const allowed = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-1/summary',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
      },
    });

    const denied = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-2/summary',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(denied).toMatchObject({
      allowed: false,
      reason_code: 'workspace_not_allowed',
      status_code: 403,
      context: {
        workspaceId: 'ws-2',
      },
    });
  });

  it('uses workspace tasks path context for workspace allowlist checks', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const allowed = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-1/tasks?limit=100&include_completed=true&task_type=execution',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(allowed).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'ig',
      },
    });

    const denied = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-2/tasks?limit=100&include_completed=true&task_type=execution',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(denied).toMatchObject({
      allowed: false,
      reason_code: 'workspace_not_allowed',
      status_code: 403,
      context: {
        workspaceId: 'ws-2',
        capabilityCode: 'ig',
      },
    });
  });

  it('uses workspace event stream path context for workspace allowlist checks', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const allowed = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-1/events/stream',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(allowed).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'ig',
      },
    });

    const denied = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/workspaces/ws-2/events/stream',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(denied).toMatchObject({
      allowed: false,
      reason_code: 'workspace_not_allowed',
      status_code: 403,
      context: {
        workspaceId: 'ws-2',
        capabilityCode: 'ig',
      },
    });
  });

  it('allows read-only IG support routes with capability context', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const headers = {
      'cf-access-jwt-assertion': token,
    };

    expect(
      isMobileWorkbenchGatewayRequestAllowed(
        '/api/v1/system-settings/keyboard-shortcuts',
        headers,
        config,
      ),
    ).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        capabilityCode: 'ig',
      },
    });

    expect(
      isMobileWorkbenchGatewayRequestAllowed(
        '/api/v1/host-resources/lanes',
        headers,
        config,
      ),
    ).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        capabilityCode: 'ig',
      },
    });
  });

  it('rejects non-read methods on bounded IG support routes', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const headers = {
      'cf-access-jwt-assertion': token,
    };

    expect(
      isMobileWorkbenchGatewayRequestAllowed(
        '/api/v1/system-settings/keyboard-shortcuts',
        headers,
        config,
        { requestMethod: 'POST' },
      ),
    ).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
      status_code: 404,
    });

    expect(
      isMobileWorkbenchGatewayRequestAllowed(
        '/api/v1/host-resources/lanes',
        headers,
        config,
        { requestMethod: 'POST' },
      ),
    ).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
      status_code: 404,
    });

    expect(
      isMobileWorkbenchGatewayRequestAllowed(
        '/api/v1/workspaces/ws-1/tasks',
        headers,
        config,
        { requestMethod: 'POST' },
      ),
    ).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
      status_code: 404,
    });

    expect(
      isMobileWorkbenchGatewayRequestAllowed(
        '/api/v1/workspaces/ws-1/events/stream',
        headers,
        config,
        { requestMethod: 'POST' },
      ),
    ).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
      status_code: 404,
    });
  });

  it('uses installed capability path context for bounded support routes', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const allowed = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/capability-packs/installed-capabilities/ig/ui-components',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(allowed).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        capabilityCode: 'ig',
      },
    });

    const allowedMpc = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/capability-packs/installed-capabilities/makeup_practice_coach/ui-components',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );
    expect(allowedMpc).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        capabilityCode: 'makeup_practice_coach',
      },
    });
  });

  it('allows Makeup Practice Coach API paths when bounded path rules match', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const allowed = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/capabilities/makeup_practice_coach/acceptance/practice-loop',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(allowed).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        capabilityCode: 'makeup_practice_coach',
      },
    });
  });

  it('allows YogaCoach API and host paths when operator workspace guardrails pass', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST: 'ws-1',
    });
    const token = createAccessJwt({
      email: 'user@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) + 3600,
    });

    const apiAllowed = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/capabilities/yogacoach/practice-review/projection',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(apiAllowed).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        capabilityCode: 'yogacoach',
      },
    });

    const hostAllowed = isMobileWorkbenchGatewayRequestAllowed(
      '/workspaces/ws-1/capability-ui-hosts/yogacoach',
      {
        'cf-access-jwt-assertion': token,
      },
      config,
    );

    expect(hostAllowed).toMatchObject({
      allowed: true,
      status_code: 200,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
      },
    });
  });

  it('rejects expired access tokens even when identity allowlist matches', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'expired@mindscape.ai',
      MOBILE_WORKBENCH_GATEWAY_JWT_CLOCK_SKEW_SECONDS: '0',
    });
    const token = createAccessJwt({
      email: 'expired@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) - 10,
      groups: ['default'],
      workspace_id: 'ws-1',
    });
    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/capability-packs/ig/ui-assets/bundle.js?workspace_id=ws-1',
      {
        CF_Authorization: `Bearer ${token}`,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'expired_or_not_ready_token',
      status_code: 403,
    });
  });

  it('collects path parse errors while staying enabled for defaults', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_EXTRA_PATH_RULES: 'badprefix,regex:^(abc',
    });
    expect(config).toMatchObject({
      enabled: true,
      reason: 'enabled_with_invalid_rules',
    });
    expect(config.errors).toEqual([
      'invalid_path_pattern:badprefix',
      'invalid_regex_pattern:regex:^(abc',
    ]);
    expect(isMobileWorkbenchGatewayPathAllowed('/workspaces/ws-1/capability-ui-hosts/ig', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/admin/tools', config)).toBe(false);
  });

  it('extracts capability scope from referer for shared workspace support paths', () => {
    expect(
      extractMobileWorkbenchGatewayRequestContext(
        '/api/v1/workspaces/ws-1/tasks?limit=20',
        {
          referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/yogacoach?component=YogaPracticeWorkbenchPage',
        },
      ),
    ).toMatchObject({
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
    });
  });

  it('enforces pack-owned workspace capability policy before allowing shared support paths', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });

    const denied = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/workspaces/ws-1/capability-ui-hosts/yogacoach',
      {
        referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/yogacoach',
      },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: false,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(denied).toMatchObject({
      allowed: false,
      reason_code: 'capability_not_allowed',
      status_code: 403,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
      },
    });

    const allowed = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/api/v1/workspaces/ws-1/tasks?limit=20',
      {
        referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/yogacoach',
      },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
      },
    });
  });

  it('ignores deprecated capability allowlist env and defers capability access to workspace policy', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_CAPABILITY_ALLOWLIST: 'ig',
    });

    const allowed = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/workspaces/ws-1/capability-ui-hosts/makeup_practice_coach',
      {
        referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/makeup_practice_coach',
      },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/makeup_practice_coach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'makeup_practice_coach',
      },
    });
  });
});

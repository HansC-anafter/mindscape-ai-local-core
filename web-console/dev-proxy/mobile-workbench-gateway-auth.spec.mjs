import crypto from 'node:crypto';
import { describe, expect, it } from 'vitest';

import {
  RSA_KEY_PAIR,
  createAccessJwt,
  createSignedAccessJwt,
  isMobileWorkbenchGatewayRequestAllowed,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.test-support.mjs';

describe('mobile workbench gateway auth policy', () => {
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
});

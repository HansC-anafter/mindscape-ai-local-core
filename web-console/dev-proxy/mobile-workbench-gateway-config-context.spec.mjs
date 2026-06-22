import { describe, expect, it } from 'vitest';

import {
  createAccessJwt,
  extractMobileWorkbenchGatewayRequestContext,
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.test-support.mjs';

describe('mobile workbench gateway config and context', () => {
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
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'missing_access_token',
    });
  });

  it('parses camelCase workspaceId and capabilityCode query parameters in request context', () => {
    expect(
      extractMobileWorkbenchGatewayRequestContext(
        '/api/v1/host/services/mobile-workbench-gateway/summary?workspaceId=ws-1&capabilityCode=yogacoach',
      ),
    ).toMatchObject({
      path: '/api/v1/host/services/mobile-workbench-gateway/summary',
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
    });
  });

  it('maps hyphenated capability API slugs back to underscore pack policy codes', () => {
    expect(
      extractMobileWorkbenchGatewayRequestContext(
        '/api/v1/capabilities/social-video-refs/runtime-config?workspace_id=ws-1&provider=youtube',
      ),
    ).toMatchObject({
      path: '/api/v1/capabilities/social-video-refs/runtime-config',
      workspaceId: 'ws-1',
      capabilityCode: 'social_video_refs',
      routeCapabilityCode: 'social-video-refs',
    });
  });

  it('maps the remote gateway control page to the target capability context', () => {
    expect(
      extractMobileWorkbenchGatewayRequestContext(
        '/workspaces/ws-1/capability-ui-hosts/mindscape_cloud_integration?component=MindscapeMobileWorkbenchGatewayPage&target_capability=yogacoach',
      ),
    ).toMatchObject({
      path: '/workspaces/ws-1/capability-ui-hosts/mindscape_cloud_integration',
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
      routeCapabilityCode: 'mindscape_cloud_integration',
      targetCapabilityCode: 'yogacoach',
      gatewayControlPlaneCarrier: true,
      gatewayControlPlaneTargeted: true,
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
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/installed-capabilities/ig/mobile-workbench-gateway-support', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/capability-packs/installed-capabilities/ig/ui-assets/bundle.js', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/workspaces/ws-1/executions?limit=50', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/workspaces/ws-1/summary', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/host-runtime/status', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/host-runtime/sessions',
      config,
      'POST',
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/turns',
      config,
      'POST',
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/events?limit=2000',
      config,
      'GET',
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/stream?last_seq=0',
      config,
      'GET',
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/agents/bridge-service',
      config,
      'GET',
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/agents/bridge-service/start',
      config,
      'POST',
    )).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(
      '/api/v1/workspaces/ws-1/agents/bridge-service/start',
      config,
      'GET',
    )).toBe(false);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/host-runtime/bridge/bridge-1', config)).toBe(false);
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
        '/api/v1/capability-packs/installed-capabilities/yogacoach/mobile-workbench-gateway-support',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/api/v1/capability-packs/installed-capabilities/yogacoach/ui-assets/1.0.0/components/YogaPracticeWorkbenchPage.mjs',
        config,
      ),
    ).toBe(true);
    expect(
      isMobileWorkbenchGatewayPathAllowed(
        '/device-link/PAIR1234?workspaceId=ws-1&sourceMode=phone',
        config,
      ),
    ).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/device-link/health', config)).toBe(false);
    expect(isMobileWorkbenchGatewayPathAllowed('/api/v1/other-service/route', config)).toBe(false);
    expect(isMobileWorkbenchGatewayPathAllowed('/workspaces/ws-1/capability-ui-hosts/performance_direction', config)).toBe(false);
  });

  it('extracts workspace and referer capability context from host-runtime session requests', () => {
    expect(
      extractMobileWorkbenchGatewayRequestContext(
        '/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/turns',
        {
          referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/ig?component=IGWorkbenchPage',
        },
      ),
    ).toMatchObject({
      path: '/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/turns',
      workspaceId: 'ws-1',
      capabilityCode: 'ig',
      referer_path: '/workspaces/ws-1/capability-ui-hosts/ig',
    });
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
    expect(isMobileWorkbenchGatewayRequestAllowed(
      '/device-link/PAIR1234?workspaceId=ws-1&sourceMode=phone',
      headers,
      config,
    )).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
      },
    });
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
});

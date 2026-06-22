import { describe, expect, it } from 'vitest';

import {
  createAccessJwt,
  isMobileWorkbenchGatewayRequestAllowed,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.test-support.mjs';

describe('mobile workbench gateway support routes', () => {
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

    expect(
      isMobileWorkbenchGatewayRequestAllowed(
        '/api/v1/host-resources/queue-utilization?live=true',
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
        '/api/v1/host-resources/queue-utilization?live=true',
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
});

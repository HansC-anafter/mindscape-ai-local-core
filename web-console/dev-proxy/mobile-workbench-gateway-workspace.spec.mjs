import { describe, expect, it } from 'vitest';

import {
  createAccessJwt,
  isMobileWorkbenchGatewayRequestAllowed,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.test-support.mjs';

describe('mobile workbench gateway workspace policy', () => {
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
});

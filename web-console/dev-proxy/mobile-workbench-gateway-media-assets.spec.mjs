import { describe, expect, it } from 'vitest';

import {
  extractMobileWorkbenchGatewayRequestContext,
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.mjs';

const MEDIA_PATH =
  '/api/v1/capabilities/video_renderer/storage/default/video_renderer/generative/ws-1/exec-1/mindscape_preview_00001_.png';
const NON_MEDIA_STORAGE_PATH =
  '/api/v1/capabilities/video_renderer/storage/default/video_renderer/generative/ws-1/exec-1/output_manifest.json';
const IG_REFERER =
  'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/ig?component=IGWorkbenchPage';

describe('mobile workbench gateway media assets', () => {
  it('allows only read-only capability storage media paths', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });

    expect(isMobileWorkbenchGatewayPathAllowed(MEDIA_PATH, config, 'GET')).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(MEDIA_PATH, config, 'HEAD')).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(MEDIA_PATH, config, 'OPTIONS')).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed(MEDIA_PATH, config, 'POST')).toBe(false);
    expect(isMobileWorkbenchGatewayPathAllowed(NON_MEDIA_STORAGE_PATH, config, 'GET')).toBe(false);
  });

  it('inherits IG workspace context for display media produced by another capability', () => {
    expect(
      extractMobileWorkbenchGatewayRequestContext(MEDIA_PATH, {
        referer: IG_REFERER,
      }),
    ).toMatchObject({
      path: MEDIA_PATH,
      workspaceId: 'ws-1',
      capabilityCode: 'ig',
      routeCapabilityCode: 'video_renderer',
      referer_path: '/workspaces/ws-1/capability-ui-hosts/ig',
    });
  });

  it('enforces the referer capability policy for cross-pack display media', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });
    const policyCalls = [];

    const allowed = await isMobileWorkbenchGatewayRequestAllowedAsync(
      MEDIA_PATH,
      { referer: IG_REFERER },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async ({ workspaceId, capabilityCode }) => {
          policyCalls.push({ workspaceId, capabilityCode });
          return {
            capabilityAllowed: capabilityCode === 'ig',
            supported: true,
            allowedPathRules: [],
          };
        },
      },
    );

    expect(policyCalls).toEqual([{ workspaceId: 'ws-1', capabilityCode: 'ig' }]);
    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'ig',
        routeCapabilityCode: 'video_renderer',
      },
    });

    const denied = await isMobileWorkbenchGatewayRequestAllowedAsync(
      MEDIA_PATH,
      { referer: IG_REFERER },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: false,
          supported: true,
          allowedPathRules: [],
        }),
      },
    );

    expect(denied).toMatchObject({
      allowed: false,
      reason_code: 'capability_not_allowed',
      status_code: 403,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'ig',
        routeCapabilityCode: 'video_renderer',
      },
    });
  });
});
